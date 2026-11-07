#!/usr/bin/env node
/**
 * W7 任务 4：对 B 的 v1.0 草图镇出评审包 —— 6 张截图（全景、合租房 1F / 2F、校园、广场、码头）+ 30 s 旁观录屏。
 *   node tools/v1map_review.mjs --api http://127.0.0.1:8091 [--port 5178] [--out report_shots/v1map] [--follow 鲸仔]
 *   需要 playwright（PLAYWRIGHT_MODULE 可指向已装好的 node_modules，例如 /home/shan-dw/Project/run/pw/node_modules/playwright）。
 * 自己起一个 Vite 开发服务（VITE_PROXY_TARGET 指到 --api），截完关掉。sector id 从 /world 的 tiles 里读，按关键词挑：
 *   合租房 share|rent|home|achan_house，校园 campus|univ|school，广场 square|plaza，码头 dock|pier|harbor。
 */
import fs from 'node:fs'
import path from 'node:path'
import { spawn } from 'node:child_process'
import { createRequire } from 'node:module'

const args = Object.fromEntries(process.argv.slice(2).map((a, i, arr) => a.startsWith('--') ? [a.slice(2), arr[i + 1] && !arr[i + 1].startsWith('--') ? arr[i + 1] : '1'] : []).filter(Boolean))
const api = args.api || 'http://127.0.0.1:8091'
const port = Number(args.port || 5178)
const out = path.resolve(args.out || 'report_shots/v1map')
const follow = args.follow || '鲸仔'
const req = createRequire(import.meta.url)
const { chromium } = req(process.env.PLAYWRIGHT_MODULE || 'playwright')
fs.mkdirSync(out, { recursive: true })

const world = await (await fetch(`${api}/world`)).json()
const sectors = [...new Set(world.tiles.map(t => t.sector).filter(Boolean))]
const arenas = [...new Set(world.tiles.map(t => t.arena).filter(Boolean))]
const pick = (res) => sectors.find(s => res.test(s)) || arenas.find(a => res.test(a)) || null
const S = {
  house: pick(/share|rent|home|achan_house|whale_home|dorm|合租/i),
  campus: pick(/campus|univ|school|college|teach|library|music|大学|校园/i),
  square: pick(/square|plaza|广场/i),
  dock: pick(/dock|pier|harbor|wharf|码头/i),
}
console.log('sectors:', sectors.join(', ')); console.log('arenas:', arenas.join(', ')); console.log('picked:', JSON.stringify(S))
const hasFloor2 = world.tiles.some(t => (t.floor ?? 1) >= 2) || Object.values((world.map && world.map.floors) || world.floors || {}).some(v => Number(v) >= 2)

const vite = spawn(process.env.npm_execpath ? 'npx' : 'npx', ['vite', '--port', String(port), '--strictPort'], { env: { ...process.env, VITE_PROXY_TARGET: api }, stdio: 'ignore', detached: true })
await new Promise(r => setTimeout(r, 4500))
const base = `http://127.0.0.1:${port}`
try {
  const browser = await chromium.launch()
  const shot = async (name, url) => {
    const p = await browser.newPage({ viewport: { width: 1920, height: 1080 } })
    await p.goto(base + url); await p.waitForFunction(() => window.__whaleStats, null, { timeout: 30000 }); await p.waitForTimeout(3500)
    await p.screenshot({ path: path.join(out, `${name}.png`) }); await p.close(); console.log('shot', name)
  }
  await shot('01_overview', '/spectate?hud=0&panel=0&thought=0&scene=world')
  if (S.house) await shot('02_house_1f', `/spectate?hud=0&panel=0&thought=0&focus=${S.house}`)
  if (S.house && hasFloor2) await shot('03_house_2f', `/spectate?hud=0&panel=0&thought=0&focus=${S.house}:2`)
  if (S.campus) await shot('04_campus', `/spectate?hud=0&panel=0&thought=0&focus=${S.campus}`)
  if (S.square) await shot('05_square', `/spectate?hud=0&panel=0&thought=0&focus=${S.square}`)
  if (S.dock) await shot('06_dock', `/spectate?hud=0&panel=0&thought=0&focus=${S.dock}`)
  // 30 s 旁观录屏（跟随）
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, recordVideo: { dir: out, size: { width: 1920, height: 1080 } } })
  const p = await ctx.newPage()
  await p.goto(`${base}/spectate?follow=${encodeURIComponent(follow)}&hud=0&layout=live&stats=1`)
  await p.waitForFunction(() => window.__whaleStats, null, { timeout: 30000 }); await p.waitForTimeout(30000)
  const v = p.video(); await ctx.close()
  const vp = await v.path(); fs.renameSync(vp, path.join(out, 'spectate_30s.webm')); console.log('video', path.join(out, 'spectate_30s.webm'))
  await browser.close()
} finally {
  try { process.kill(-vite.pid) } catch { try { vite.kill() } catch { /* */ } }
}
