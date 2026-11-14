/**
 * Godot 六角色条带的 Phaser 加载：/art/chars/<key>.json → 每个动画一张横排条 → spritesheet + anims。
 * 开关：URL `?chars=old` 或 localStorage.godotChars === 'off' 退回旧人物表。清单 404（/art 没挂）时自动退回。
 */
import Phaser from 'phaser'
import { ART_BASE, GODOT_CHAR_KEYS, parseGodotCharManifest, type GodotCharKey, type GodotCharManifest } from './godotChars'

const manifests = new Map<GodotCharKey, GodotCharManifest>()

export function godotCharsEnabled(): boolean {
  try {
    if (new URLSearchParams(window.location.search).get('chars') === 'old') return false
    if (localStorage.getItem('godotChars') === 'off') return false
  } catch { /* ignore */ }
  return true
}
export const godotCharTex = (key: string, anim: string) => `gchar_${key}_${anim}`
export const godotCharAnim = (key: string, anim: string) => `gchar_${key}_${anim}`
export function godotCharManifest(key: GodotCharKey): GodotCharManifest | null { return manifests.get(key) ?? null }

/** preload()：先拉六份清单，清单到了再把条带排进同一轮加载 */
export function preloadGodotChars(scene: Phaser.Scene) {
  if (!godotCharsEnabled()) return
  for (const key of GODOT_CHAR_KEYS) {
    if (manifests.has(key)) { queueStrips(scene, key, manifests.get(key)!); continue }
    const jk = `gchar_manifest_${key}`
    scene.load.json(jk, `${ART_BASE}/chars/${key}.json`)
    scene.load.once(`filecomplete-json-${jk}`, (_k: string, _t: string, data: unknown) => {
      const m = parseGodotCharManifest(data)
      if (!m) { console.warn('[godotChars] bad manifest', key); return }
      manifests.set(key, m)
      queueStrips(scene, key, m)
    })
  }
}
function queueStrips(scene: Phaser.Scene, key: GodotCharKey, m: GodotCharManifest) {
  for (const [anim, a] of Object.entries(m.animations)) {
    const tk = godotCharTex(key, anim)
    if (scene.textures.exists(tk)) continue
    scene.load.spritesheet(tk, `${ART_BASE}/chars/${m.images_dir}/${a.file}`, { frameWidth: m.frame_w, frameHeight: m.frame_h })
  }
}

/** create()：建动画（幂等）；像素风 NEAREST 由 pixelArt 全局配置保证 */
export function createGodotCharAnimations(scene: Phaser.Scene) {
  for (const [key, m] of manifests) {
    for (const [anim, a] of Object.entries(m.animations)) {
      const tk = godotCharTex(key, anim), ak = godotCharAnim(key, anim)
      if (!scene.textures.exists(tk) || scene.anims.exists(ak)) continue
      scene.anims.create({ key: ak, frames: scene.anims.generateFrameNumbers(tk, { start: 0, end: a.frames - 1 }), frameRate: a.fps, repeat: a.loop ? -1 : 0 })
    }
  }
}
/** 该角色是否已就位（清单 + idle 条带） */
export function godotCharReady(scene: Phaser.Scene, key: GodotCharKey): boolean {
  return godotCharsEnabled() && manifests.has(key) && scene.textures.exists(godotCharTex(key, 'idle'))
}
