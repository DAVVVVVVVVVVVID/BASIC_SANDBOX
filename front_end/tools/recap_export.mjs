#!/usr/bin/env node
/**
 * Q1「她的一天」回顾视频一键导出：
 *   node tools/recap_export.mjs --date 2026-11-06 [--town main] [--seconds 75] [--base http://127.0.0.1:5174] [--out /home/shan-dw/Project/run/data/recap]
 * 用 Playwright 无头打开 /replay?recap=1&export=1，等 MediaRecorder 的 webm 下载完成，存到 <out>/<date>.webm（多镇：<date>_<town>.webm）。
 * 需要 playwright（npm i -D playwright && npx playwright install chromium），或设 PLAYWRIGHT_MODULE 指到已装好的 node_modules/playwright。
 */
import fs from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'

const args = Object.fromEntries(process.argv.slice(2).map((a, i, arr) => a.startsWith('--') ? [a.slice(2), arr[i + 1] && !arr[i + 1].startsWith('--') ? arr[i + 1] : '1'] : []).filter(Boolean))
const date = args.date || new Date(Date.now() - 86400000).toISOString().slice(0, 10)
const town = args.town || 'main'
const seconds = Number(args.seconds || 75)
const base = args.base || 'http://127.0.0.1:5174'
const outDir = args.out || '/home/shan-dw/Project/run/data/recap'
const req = createRequire(import.meta.url)
const pwPath = process.env.PLAYWRIGHT_MODULE || 'playwright'
const { chromium } = req(pwPath)

fs.mkdirSync(outDir, { recursive: true })
const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1680, height: 1000 }, acceptDownloads: true })
const page = await ctx.newPage()
const url = `${base}/replay?town=${encodeURIComponent(town)}&date=${date}&recap=1&export=1&seconds=${seconds}`
console.log('open', url)
await page.goto(url)
await page.waitForFunction(() => /数据：/.test(document.body.innerText), null, { timeout: 60000 })
console.log(await page.evaluate(() => document.body.innerText.split('\n').find(l => l.startsWith('数据：'))))
const dl = await page.waitForEvent('download', { timeout: (seconds + 30) * 1000 })
const out = path.join(outDir, town === 'main' ? `${date}.webm` : `${date}_${town}.webm`)
await dl.saveAs(out)
const st = fs.statSync(out)
console.log('saved', out, `${(st.size / 1048576).toFixed(1)} MB`)
await browser.close()
