import { defineConfig, loadEnv, Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
import path from 'node:path'
import type { IncomingMessage, ServerResponse } from 'node:http'

/** 读 run/towns.yaml 里 towns.<name>.k（最小解析，不引 yaml 依赖）：沙盒端口 = 8000 + 10k */
function readTowns(file: string): Record<string, number> {
  const out: Record<string, number> = {}
  let text = ''
  try { text = fs.readFileSync(file, 'utf8') } catch { return out }
  const lines = text.split('\n')
  let inTowns = false
  let cur: string | null = null
  for (const raw of lines) {
    const line = raw.replace(/#.*$/, '')
    if (/^towns:\s*$/.test(line)) { inTowns = true; continue }
    if (!inTowns) continue
    if (/^\S/.test(line) && line.trim()) break            // 顶层下一个键
    const m1 = /^ {2}([A-Za-z0-9_-]+):\s*$/.exec(line)
    if (m1) { cur = m1[1]; continue }
    const m2 = /^ {4}k:\s*(\d+)/.exec(line)
    if (m2 && cur) out[cur] = Number(m2[1])
  }
  return out
}

/** 只读静态目录：/<prefix>/<相对路径> → 目录下的 .json / .jsonl / .png / .gif / .mp4 / .webm（回放页与游戏机小窗用） */
function readOnlyDir(prefix: string, root: string): Plugin {
  const ok = /\.(jsonl?|png|gif|mp4|webm|txt|md)$/i
  const handler = (req: IncomingMessage, res: ServerResponse, next: () => void) => {
    const url = (req.url || '').split('?')[0]
    if (!url.startsWith(prefix + '/')) return next()
    const rel = decodeURIComponent(url.slice(prefix.length + 1))
    const abs = path.resolve(root, rel)
    if (!abs.startsWith(path.resolve(root) + path.sep)) { res.statusCode = 403; res.end(); return }
    if (rel.endsWith('/') || rel === '') {
      // 目录列表（JSON）
      try {
        const items = fs.readdirSync(abs, { withFileTypes: true }).map(e => ({ name: e.name, dir: e.isDirectory() }))
        res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(items))
      } catch { res.statusCode = 404; res.end() }
      return
    }
    if (!ok.test(abs) || !fs.existsSync(abs) || !fs.statSync(abs).isFile()) { res.statusCode = 404; res.end(); return }
    const type = abs.endsWith('.json') ? 'application/json' : abs.endsWith('.jsonl') ? 'application/x-ndjson'
      : abs.endsWith('.md') ? 'text/markdown' : abs.endsWith('.png') ? 'image/png' : abs.endsWith('.gif') ? 'image/gif' : abs.endsWith('.mp4') ? 'video/mp4' : abs.endsWith('.webm') ? 'video/webm' : 'text/plain'
    res.setHeader('Content-Type', type + (type.startsWith('text') || type.includes('json') ? '; charset=utf-8' : ''))
    res.setHeader('Cache-Control', 'no-store')
    fs.createReadStream(abs).pipe(res)
  }
  return {
    name: `readonly-dir:${prefix}`,
    configureServer(server) { server.middlewares.use(handler) },
    configurePreviewServer(server) { server.middlewares.use(handler) },
  }
}

// E3：前端只访问相对路径 `/api/...`，由 Vite dev / preview 的 server.proxy 转到后端。
// 后端继续只监听 127.0.0.1:8000；局域网里的直播机只需访问前端主机（ARCHITECTURE §1.2 硬规则）。
//   VITE_API_BASE      前端请求前缀，默认 `/api`（改成 http://host:8000 可绕过代理直连）
//   VITE_PROXY_TARGET  代理目标，默认 http://127.0.0.1:8000
//   VITE_PORT          开发端口，默认 5173（运行台）；自测用 `npm run dev -- --port 5174`
//   VITE_OBSERVE_BASE  思考字幕请求前缀，默认 `/observe`（E8）
//   VITE_OBSERVE_TARGET C 的只读观察面板，默认 http://127.0.0.1:8002（路径不改写：/observe/latest 原样转发）
//   VITE_TOWNS_YAML    多镇表（E14），默认 /home/shan-dw/Project/run/towns.yaml：/t/<town>/api → 127.0.0.1:(8000+10k)
//   VITE_DATASET_DIR   A 的每日导出目录（E13 回放页只读），默认 /home/shan-dw/Project/whale-self/data/dataset → /dataset/
//   VITE_SANDBOX_DATA_DIR  主镇沙盒数据目录（行动 / 聊天 JSONL，只读），默认 /home/shan-dw/Project/run/data/sandbox → /sandboxdata/
//   VITE_GAME_RUNS_DIR D 的 runs 目录（游戏机小窗读回放 GIF，只读），默认 /home/shan-dw/Project/whale-game/runs → /gameruns/
//   VITE_SELF_DAYS_DIR A 的日摘要目录（Q1 回顾视频字幕，只读），默认 /home/shan-dw/Project/whale-self/data/self/whale/memory/days → /selfdays/
//   VITE_SELF_MEMORY_DIR 她的记忆目录（/brain 页点开记忆全文，只读 .md），默认 /home/shan-dw/Project/whale-self/data/self/whale/memory → /selfmem/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiBase = (env.VITE_API_BASE || '/api').replace(/\/$/, '')
  const target = env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000'
  const observeBase = (env.VITE_OBSERVE_BASE || '/observe').replace(/\/$/, '')
  const observeTarget = env.VITE_OBSERVE_TARGET || 'http://127.0.0.1:8002'
  const towns = readTowns(env.VITE_TOWNS_YAML || '/home/shan-dw/Project/run/towns.yaml')
  const townProxy: Record<string, unknown> = {}
  for (const [name, k] of Object.entries(towns)) {
    if (k === 0) continue
    const port = 8000 + 10 * k
    townProxy[`/t/${name}/api`] = {
      target: `http://127.0.0.1:${port}`, changeOrigin: true, ws: true,
      rewrite: (p: string) => p.replace(new RegExp(`^/t/${name}/api`), '') || '/',
    }
  }
  const proxy = apiBase.startsWith('/')
    ? {
        [apiBase]: {
          target,
          changeOrigin: true,
          ws: true,
          rewrite: (p: string) => p.replace(new RegExp(`^${apiBase}`), '') || '/',
        },
        ...(observeBase.startsWith('/') ? { [observeBase]: { target: observeTarget, changeOrigin: true } } : {}),
        ...townProxy,
      }
    : undefined

  return {
    plugins: [
      react(),
      readOnlyDir('/dataset', env.VITE_DATASET_DIR || '/home/shan-dw/Project/whale-self/data/dataset'),
      readOnlyDir('/sandboxdata', env.VITE_SANDBOX_DATA_DIR || '/home/shan-dw/Project/run/data/sandbox'),
      readOnlyDir('/gameruns', env.VITE_GAME_RUNS_DIR || '/home/shan-dw/Project/whale-game/runs'),
      readOnlyDir('/selfdays', env.VITE_SELF_DAYS_DIR || '/home/shan-dw/Project/whale-self/data/self/whale/memory/days'),
      readOnlyDir('/selfmem', env.VITE_SELF_MEMORY_DIR || '/home/shan-dw/Project/whale-self/data/self/whale/memory'),
    ],
    server: {
      host: true,                 // 监听 0.0.0.0，局域网可达
      // tools/.venv（几千个文件）、data/、报告截图、参考图不参与热更新，否则 inotify 配额会被吃光（ENOSPC）
      watch: { ignored: ['**/tools/.venv/**', '**/data/**', '**/report_shots/**', '**/ref/**', '**/public/assets/gen-ai/review/**'] },
      port: Number(env.VITE_PORT) || 5173,
      strictPort: false,
      proxy,
    },
    preview: {
      host: true,
      port: Number(env.VITE_PORT) || 5173,
      proxy,
    },
    build: {
      target: 'es2020',
      sourcemap: false,
      chunkSizeWarningLimit: 1500,
      rollupOptions: { output: { manualChunks: { phaser: ['phaser'], react: ['react', 'react-dom', 'zustand'] } } },
    },
  }
})
