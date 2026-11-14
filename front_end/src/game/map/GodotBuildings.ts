/**
 * 建筑整栋外观贴图（Godot 同步③，移植 BuildingsLayer.gd）：每栋一张 PNG，底边锁占地下沿、水平居中、与人物物品同层按底边 y 排序；
 * 取景那栋隐藏外观露出室内瓦片；可选夜间亮窗层（ADD 混合，按 nightFactor 淡入淡出）。
 */
import Phaser from 'phaser'
import type { GameObject } from '../../types'
import { TILE_SIZE } from '../constants'
import { buildingForNames, facadeLayout, hasFacadeAnchor, type BuildingBox } from '../godotMap'
import { godotBuildings, godotBuildingSpec, godotBuildingTex } from '../godotMapLoad'

export interface FacadeHolder { key: string; keys: string[]; id: string; container: Phaser.GameObjects.Container; night: Phaser.GameObjects.Image | null; rect: Phaser.Geom.Rectangle; depth: number }

export default class GodotBuildings {
  private holders: FacadeHolder[] = []
  private focus = ''

  constructor(private scene: Phaser.Scene) {}

  /** 哪些 key 有外观（屋顶瓦片 / 室内瓦片要按 focus-only 处理） */
  static facadedKeys(boxes: BuildingBox[]): Set<string> {
    const m = godotBuildings(); const out = new Set<string>()
    if (!m) return out
    for (const b of boxes) if (hasFacadeAnchor(m, b.key, b.id)) out.add(b.key)
    return out
  }

  rebuild(boxes: BuildingBox[], objects: GameObject[]) {
    this.destroy()
    const m = godotBuildings(); if (!m) return
    const T = TILE_SIZE
    const columnHasObject = (x: number, y0: number, y1: number) => objects.some(o => (o.tiles && o.tiles.length ? o.tiles : [o.position]).some(c => c.x === x && c.y >= y0 && c.y <= y1))
    for (const b of boxes) {
      const ent = buildingForNames(m, [b.key, b.id])
      if (!ent || !hasFacadeAnchor(m, b.key, b.id)) continue
      const spec = godotBuildingSpec(ent.id); if (!spec) continue
      const texKey = godotBuildingTex(spec.image)
      if (!this.scene.textures.exists(texKey)) { console.warn('[godotBuildings] image missing', ent.id); continue }
      const src = this.scene.textures.get(texKey).getSourceImage() as { width: number; height: number }
      const L = facadeLayout(spec, b, src.width, src.height, T, columnHasObject)
      const holder = this.scene.add.container(L.cx, L.bottom)
      if (spec.backing) {
        const g = this.scene.add.graphics(); g.fillStyle(Phaser.Display.Color.HexStringToColor(spec.backing).color, 1).fillRect(-L.W * T * 0.5, -L.H * T, L.W * T, L.H * T)
        holder.add(g)
      }
      const mk = (key: string) => {
        const img = this.scene.add.image(-L.w * 0.5 + L.shift + L.clipL, -L.h, key).setOrigin(0, 0).setScale(L.sx, L.sy)
        if (L.clipL > 0 || L.clipR > 0) img.setCrop(L.clipL / L.sx, 0, src.width - (L.clipL + L.clipR) / L.sx, src.height)
        return img
      }
      const img = mk(texKey)
      holder.add(img)
      let night: Phaser.GameObjects.Image | null = null
      if (spec.night_image && this.scene.textures.exists(godotBuildingTex(spec.night_image))) {
        night = mk(godotBuildingTex(spec.night_image)).setBlendMode(Phaser.BlendModes.ADD).setAlpha(0)
        holder.add(night)
      }
      holder.setDepth(L.bottom)   // 与人物 / 物品同层：底边 y 排序
      const rect = new Phaser.Geom.Rectangle(L.cx - L.w * 0.5 + L.shift + L.clipL, L.bottom - L.h, L.w - L.clipL - L.clipR, L.h)
      this.holders.push({ key: b.key, keys: ent.keys, id: ent.id, container: holder, night, rect, depth: L.bottom })
    }
    this.applyFocus(this.focus)
    console.debug('[godotBuildings]', this.holders.length, 'facades')
  }

  /** 取景 key（Godot 口径）∈ 这栋的 keys → 隐藏外观 */
  applyFocus(key: string) {
    this.focus = key
    for (const h of this.holders) h.container.setVisible(!(key && h.keys.includes(key)))
  }
  setNight(a: number) { for (const h of this.holders) h.night?.setAlpha(a) }
  all(): FacadeHolder[] { return this.holders }

  destroy() {
    for (const h of this.holders) h.container.destroy(true)
    this.holders = []
  }
}
