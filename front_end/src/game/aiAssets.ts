/**
 * W8 美术管线产物（public/assets/gen-ai/，由 tools/gen_assets_ai.py 生成）的加载与开关。
 *   manifest.json = { tile_px, backdrops: { <name>: {sector, floor, view, x0, y0, w, h, px, tile_px, qa_score} }, objects: [type, ...] }
 * 开关：URL `&ai=0` 或 localStorage.aiAssets === 'off' 关闭（评审页「一键替换」切这个）。
 */
export interface AiBackdrop { sector: string; floor: number; view: 'interior' | 'exterior'; x0: number; y0: number; w: number; h: number; px: number; tile_px: number; qa_score?: number }
export interface AiManifest { tile_px: number; backdrops: Record<string, AiBackdrop>; objects: string[] }

let manifest: AiManifest | null = null
export function aiEnabled(): boolean {
  try {
    if (new URLSearchParams(window.location.search).get('ai') === '0') return false
    if (localStorage.getItem('aiAssets') === 'off') return false
  } catch { /* ignore */ }
  return true
}
export function setAiEnabled(on: boolean) { try { localStorage.setItem('aiAssets', on ? 'on' : 'off') } catch { /* ignore */ } }
export function getAiManifest() { return manifest }

export async function loadAiManifest(): Promise<AiManifest | null> {
  if (manifest) return manifest
  try {
    const res = await fetch('assets/gen-ai/manifest.json', { cache: 'no-store' })
    if (!res.ok) return null
    const m = (await res.json()) as AiManifest
    if (!m || typeof m !== 'object' || !m.backdrops) return null
    manifest = { tile_px: m.tile_px || 32, backdrops: m.backdrops || {}, objects: Array.isArray(m.objects) ? m.objects : [] }
    return manifest
  } catch { return null }
}

export const aiBackdropKey = (name: string) => `aibg_${name}`
export const aiObjectKey = (type: string) => `aiobj_${type}`

/** 预加载（幂等）；没 manifest 或开关关着就什么都不加载 */
export function preloadAiAssets(scene: Phaser.Scene) {
  if (!manifest || !aiEnabled()) return
  for (const name of Object.keys(manifest.backdrops)) {
    if (!scene.textures.exists(aiBackdropKey(name))) scene.load.image(aiBackdropKey(name), `assets/gen-ai/backdrops/${name}.png`)
  }
  for (const t of manifest.objects) {
    if (!scene.textures.exists(aiObjectKey(t))) scene.load.image(aiObjectKey(t), `assets/gen-ai/objects/${t}.png`)
  }
}
