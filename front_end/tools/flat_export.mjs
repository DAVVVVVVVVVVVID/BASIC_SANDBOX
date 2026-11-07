#!/usr/bin/env node
/**
 * W8 管线第一步：从 B 的草图镇导出各区域的平涂版式图（整数倍 tile）。
 *   node tools/flat_export.mjs --api http://127.0.0.1:8091 --regions home:1:interior,home:1:exterior,home:2:interior,university:1:exterior,... [--px 32] [--out data/assets/flats] [--port 5179]
 *   region = <sector或arena>:<floor>:<interior|exterior>
 * 输出 <out>/<sector>_<floor>f_<view>.png + 同名 .json（x0,y0,w,h,px,mapVersion）。
 */
import fs from 'node:fs'
import path from 'node:path'
import { spawn } from 'node:child_process'
import { createRequire } from 'node:module'
const args = Object.fromEntries(process.argv.slice(2).map((a, i, arr) => a.startsWith('--') ? [a.slice(2), arr[i + 1] && !arr[i + 1].startsWith('--') ? arr[i + 1] : '1'] : []).filter(Boolean))
const api = args.api || 'http://127.0.0.1:8091'
const port = Number(args.port || 5179)
const px = Number(args.px || 32)
const out = path.resolve(args.out || 'data/assets/flats')
const regions = (args.regions || 'home:1:interior').split(',').map(s => s.trim()).filter(Boolean)
const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || 'playwright')
fs.mkdirSync(out, { recursive: true })
const vite = spawn('npx', ['vite', '--port', String(port), '--strictPort'], { env: { ...process.env, VITE_PROXY_TARGET: api }, stdio: 'ignore', detached: true })
await new Promise(r => setTimeout(r, 4500))
try {
  const browser = await chromium.launch(); const page = await browser.newPage({ viewport: { width: 2400, height: 2000 } })
  for (const r of regions) {
    const [sector, floor = '1', view = 'interior'] = r.split(':')
    await page.goto(`http://127.0.0.1:${port}/flat?sector=${encodeURIComponent(sector)}&floor=${floor}&view=${view}&px=${px}`)
    await page.waitForFunction(() => window.__flatMeta, null, { timeout: 30000 })
    const meta = await page.evaluate(() => window.__flatMeta)
    const name = `${sector}_${floor}f_${view}`
    await page.locator('canvas').screenshot({ path: path.join(out, `${name}.png`), omitBackground: true })
    fs.writeFileSync(path.join(out, `${name}.json`), JSON.stringify(meta, null, 2))
    console.log('flat', name, `${meta.w}x${meta.h} tiles @${px}px`)
  }
  await browser.close()
} finally { try { process.kill(-vite.pid) } catch { try { vite.kill() } catch { /* */ } } }
