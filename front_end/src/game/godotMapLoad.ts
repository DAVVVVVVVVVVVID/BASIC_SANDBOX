/**
 * Godot 地图素材的 Phaser 加载：map_rules.json、tiles/<preset>.json(+png) 与 fallback 套、objects/manifest.json(+预设叠加) 与物品图。
 * 查找顺序同 AssetLib：/art（whale-godot/assets/ext，本地放不进 git）→ /art0（仓库内置 assets）。
 * 开关：URL `?tiles=old` 或 localStorage.godotMap === 'off' 退回旧地砖 / 旧物品图；规则或图集 404 自动退回。
 */
import Phaser from 'phaser'
import { ART_BASE } from './godotChars'
import { mergeObjectsMeta, objectEntry, objectImage, type MapRules, type ObjectsMeta, type TilesMeta } from './godotMap'

export const ART_BASE0 = '/art0'
export const GODOT_TILES_PRESET = 'fantasy-outdoor'

let rules: MapRules | null = null
let tilesMain: TilesMeta | null = null
let tilesFb: TilesMeta | null = null
let objectsMeta: ObjectsMeta | null = null
let objectsOver: Partial<ObjectsMeta> | null = null
const queuedImages = new Set<string>()

export function godotMapEnabled(): boolean {
  try {
    if (new URLSearchParams(window.location.search).get('tiles') === 'old') return false
    if (localStorage.getItem('godotMap') === 'off') return false
  } catch { /* ignore */ }
  return true
}
export const godotTilesTex = (src: 'main' | 'fb') => `gtiles_${src}`
export const godotObjectTex = (image: string) => `gobj_${image.replace(/[^a-zA-Z0-9_.-]/g, '_')}`
export function godotRules() { return rules }
export function godotTiles() { return tilesMain }
export function godotTilesFallback() { return tilesFb }
export function godotObjects(): ObjectsMeta | null { return objectsMeta ? mergeObjectsMeta(objectsMeta, objectsOver) : null }
/** 规则 + 主图集都就位才算可用 */
export function godotMapReady(scene: Phaser.Scene): boolean {
  return godotMapEnabled() && !!rules && !!tilesMain && scene.textures.exists(godotTilesTex('main'))
}

function parseTiles(raw: unknown): TilesMeta | null {
  const r = raw as Partial<TilesMeta> | null
  if (!r || typeof r !== 'object' || !r.index || typeof r.index !== 'object') return null
  return { image: String(r.image ?? ''), tile: Number(r.tile) || 48, columns: Number(r.columns) || 8, filter: r.filter, fallback: r.fallback, index: r.index, variants: r.variants ?? {}, base: r.base ?? {}, autotile: Array.isArray(r.autotile) ? r.autotile : [], overlay: r.overlay ?? {}, object_overlays: Array.isArray(r.object_overlays) ? r.object_overlays : [] }
}

/**
 * preload()：排队 json → 到了再排图。objectTypes = 场上物品类型（只拉用到的图）。幂等，可在换图重建时再调。
 */
export function preloadGodotMap(scene: Phaser.Scene, objectTypes: string[]) {
  if (!godotMapEnabled()) return
  const L = scene.load
  const once = (jk: string, url: string, cb: (data: unknown) => void) => {
    if (scene.cache.json.exists(jk)) { cb(scene.cache.json.get(jk)); return }
    L.json(jk, url)
    L.once(`filecomplete-json-${jk}`, (_k: string, _t: string, data: unknown) => cb(data))
  }
  if (!rules) once('gmap_rules', `${ART_BASE0}/map_rules.json`, d => { rules = (d && typeof d === 'object') ? d as MapRules : null })
  if (!tilesMain) {
    once(`gmap_tiles_${GODOT_TILES_PRESET}`, `${ART_BASE}/tiles/${GODOT_TILES_PRESET}.json`, d => {
      tilesMain = parseTiles(d)
      if (!tilesMain) { console.warn('[godotMap] bad tiles json'); return }
      if (!scene.textures.exists(godotTilesTex('main'))) L.image(godotTilesTex('main'), `${ART_BASE}/tiles/${tilesMain.image}`)
      const fb = tilesMain.fallback
      if (fb && fb !== GODOT_TILES_PRESET) {
        once(`gmap_tiles_${fb}`, `${ART_BASE0}/tiles/${fb}.json`, d2 => {
          tilesFb = parseTiles(d2)
          if (tilesFb && tilesFb.tile === tilesMain!.tile && !scene.textures.exists(godotTilesTex('fb'))) L.image(godotTilesTex('fb'), `${ART_BASE0}/tiles/${tilesFb.image}`)
          else tilesFb = null
        })
      }
    })
  }
  const queueObjects = () => {
    const meta = godotObjects(); if (!meta) return
    for (const type of new Set(objectTypes)) {
      const e = objectEntry(meta, type); if (!e) continue
      for (const img of (e.variants && e.variants.length ? e.variants : [e.image])) {
        const key = godotObjectTex(img)
        if (queuedImages.has(key) || scene.textures.exists(key)) continue
        queuedImages.add(key)
        L.image(key, `${ART_BASE}/objects/${img}`)
      }
    }
  }
  if (!objectsMeta) {
    once('gmap_objects', `${ART_BASE}/objects/manifest.json`, d => {
      const r = d as ObjectsMeta | null
      objectsMeta = r && r.items ? r : null
      once(`gmap_objects_${GODOT_TILES_PRESET}`, `${ART_BASE}/objects/manifest.${GODOT_TILES_PRESET}.json`, d2 => { objectsOver = (d2 && typeof d2 === 'object') ? d2 as Partial<ObjectsMeta> : null; queueObjects() })
    })
  } else queueObjects()
  // 物品图 /art 没有 → 退到 /art0（仓库内置的基础图）
  if (!(L as unknown as { __godotErrHook?: boolean }).__godotErrHook) {
    ;(L as unknown as { __godotErrHook?: boolean }).__godotErrHook = true
    L.on('loaderror', (file: { key: string; url: string; type: string }) => {
      if (file.type === 'image' && file.key.startsWith('gobj_') && String(file.url).startsWith(`${ART_BASE}/`)) {
        L.image(file.key, String(file.url).replace(ART_BASE + '/', ART_BASE0 + '/'))
      }
    })
  }
}

/** 物品图是否就位（含变体） */
export function godotObjectTexFor(scene: Phaser.Scene, type: string, x: number, y: number): { key: string; entry: ReturnType<typeof objectEntry>; pxPerTile: number } | null {
  const meta = godotObjects(); if (!meta || !godotMapEnabled()) return null
  const e = objectEntry(meta, type); if (!e) return null
  const key = godotObjectTex(objectImage(e, x, y))
  if (!scene.textures.exists(key)) return null
  return { key, entry: e, pxPerTile: Number(e.px_per_tile ?? e.tile_px ?? meta.tile_px ?? 96) }
}
