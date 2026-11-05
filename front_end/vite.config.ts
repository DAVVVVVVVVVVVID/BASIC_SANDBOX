import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// E3：前端只访问相对路径 `/api/...`，由 Vite dev / preview 的 server.proxy 转到后端。
// 后端继续只监听 127.0.0.1:8000；局域网里的直播机只需访问前端主机（ARCHITECTURE §1.2 硬规则）。
//   VITE_API_BASE      前端请求前缀，默认 `/api`（改成 http://host:8000 可绕过代理直连）
//   VITE_PROXY_TARGET  代理目标，默认 http://127.0.0.1:8000
//   VITE_PORT          开发端口，默认 5173（运行台）；自测用 `npm run dev -- --port 5174`
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiBase = (env.VITE_API_BASE || '/api').replace(/\/$/, '')
  const target = env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000'
  const proxy = apiBase.startsWith('/')
    ? {
        [apiBase]: {
          target,
          changeOrigin: true,
          ws: true,
          rewrite: (p: string) => p.replace(new RegExp(`^${apiBase}`), '') || '/',
        },
      }
    : undefined

  return {
    plugins: [react()],
    server: {
      host: true,                 // 监听 0.0.0.0，局域网可达
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
