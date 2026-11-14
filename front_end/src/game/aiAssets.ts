/**
 * W8 美术管线产物（public/assets/gen-ai/，由 tools/gen_assets_ai.py 生成）的加载与开关。
 *   manifest.json = { tile_px, backdrops: { <name>: {sector, floor, view, x0, y0, w, h, px, tile_px, qa_score} }, objects: [type, ...] }
 * 开关：URL `&ai=0` 或 localStorage.aiAssets === 'off' 关闭（评审页「一键替换」切这个）。
 */
export interface AiBackdrop { sector: string; floor: number; view: 'interior' | 'exterior'; x0: number; y0: number; w: number; h: number; px: number; tile_px: number; qa_score?: number; margin?: number }
export interface AiTiles { image: string; tile: number; columns: number; index: Record<string, number>; variants: Record<string, string[]> }
export interface AiManifest { tile_px: number; backdrops: Record<string, AiBackdrop>; objects: string[]; chars: string[]; char_frame: [number, number]; deco: string[]; tiles: AiTiles | null }
/** AI 角色表帧尺寸（4 列 × 5 行，行列含义与自制像素表相同，见 assets.ts CHAR_ROWS / POSE_ROW） */
export const AI_CHAR_FRAME = { w: 32, h: 48 }

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
    manifest = { tile_px: m.tile_px || 32, backdrops: m.backdrops || {}, objects: Array.isArray(m.objects) ? m.objects : [], chars: Array.isArray(m.chars) ? m.chars : [], char_frame: Array.isArray(m.char_frame) && m.char_frame.length === 2 ? m.char_frame : [AI_CHAR_FRAME.w, AI_CHAR_FRAME.h], deco: Array.isArray(m.deco) ? m.deco : [], tiles: m.tiles && typeof m.tiles === 'object' && m.tiles.index ? m.tiles : null }
    return manifest
  } catch { return null }
}

/** 物品类型别名：没有专属 AI 图的类型借同类图（bed_21 借 bed 并旋转 90°，见 GameObjectSprite） */
export const AI_OBJECT_ALIAS: Record<string, string> = { pc_desk: 'pc', book: 'shelf', sofa: 'sofa_tv', cook: 'stove', desk: 'classroom_desk', bed_21: 'bed', desk_12: 'reading_desk', game_console: 'pc', dining_table: 'restaurant_table', tree_big: 'tree', bench_side: 'bench_side_e' }   // bench_side：v1.2.3 码头侧向长椅（B 定座面朝东 → 镜像版 _e）   // tree_big：v1.2 大树 2×2，正式图待主播，先用小树图（按 tiles 包围盒底边对齐）   // dining_table：B f4d42ba 合租房家用餐桌（2×1），沿用餐馆桌子图
export function aiObjectTypeFor(type: string): string { return AI_OBJECT_ALIAS[type] ?? type.replace(/_\d+$/, '') }
/** 该类型有 AI 物品图（manifest.objects 里）→ 不必再去拉像素 sprite（v1.2 的 lamp 没有像素图，拉了只会报 404） */
export function aiHasObject(type: string): boolean { return !!manifest && aiEnabled() && manifest.objects.includes(aiObjectTypeFor(type)) }

export const aiBackdropKey = (name: string) => `aibg_${name}`
export const aiObjectKey = (type: string) => `aiobj_${type}`
export const aiCharKey = (key: string) => `aichar_${key}`
export const AI_TILES_KEY = 'aitiles'
export const aiDecoKey = (name: string) => `aideco_${name}`
/** 像素表的 _v1 / _v2 后缀不区分，AI 表只有一套 */
export const aiCharBase = (key: string) => key.replace(/_v\d+$/, '')

/** 预加载（幂等）；没 manifest 或开关关着就什么都不加载 */
export function preloadAiAssets(scene: Phaser.Scene) {
  if (!manifest || !aiEnabled()) return
  for (const name of Object.keys(manifest.backdrops)) {
    if (!scene.textures.exists(aiBackdropKey(name))) scene.load.image(aiBackdropKey(name), `assets/gen-ai/backdrops/${name}.png`)
  }
  for (const t of manifest.objects) {
    if (!scene.textures.exists(aiObjectKey(t))) scene.load.image(aiObjectKey(t), `assets/gen-ai/objects/${t}.png`)
  }
  const [fw, fh] = manifest.char_frame
  for (const k of manifest.chars) {
    if (!scene.textures.exists(aiCharKey(k))) scene.load.spritesheet(aiCharKey(k), `assets/gen-ai/chars/${k}.png`, { frameWidth: fw, frameHeight: fh })
  }
  if (manifest.tiles && !scene.textures.exists(AI_TILES_KEY)) scene.load.spritesheet(AI_TILES_KEY, `assets/gen-ai/${manifest.tiles.image}`, { frameWidth: manifest.tiles.tile, frameHeight: manifest.tiles.tile })
  for (const d of manifest.deco) {
    if (!scene.textures.exists(aiDecoKey(d))) scene.load.image(aiDecoKey(d), `assets/gen-ai/deco/${d}.png`)
  }
}

/** AI 素材全部是高清原画（96 px/格、角色 96×144/帧、地砖 48 px/格）：用线性过滤，不要 pixelArt 的 NEAREST（主播 11-07：不必像素风） */
export function setAiTexturesLinear(scene: Phaser.Scene) {
  if (!manifest) return
  const keys = [...Object.keys(manifest.backdrops).map(aiBackdropKey), ...manifest.objects.map(aiObjectKey), ...manifest.chars.map(aiCharKey), ...manifest.deco.map(aiDecoKey), AI_TILES_KEY]
  for (const k of keys) if (scene.textures.exists(k)) scene.textures.get(k).setFilter(Phaser.Textures.FilterMode.LINEAR)
}

/** 确定性哈希（0..1），地砖变体 / 装饰撒点都用它，刷新不会变 */
export function tileHash(x: number, y: number, salt = 0): number {
  let h = (x * 374761393 + y * 668265263 + salt * 1442695041) | 0
  h = (h ^ (h >>> 13)) * 1274126177
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295
}
