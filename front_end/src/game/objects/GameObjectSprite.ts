import Phaser from 'phaser'
import { GameObject } from '../../types'
import { tileToPixel, TILE_SIZE } from '../map/TileMap'
import { objTextureKey } from '../assets'
import { aiObjectKey, aiEnabled, aiObjectTypeFor, getAiManifest } from '../aiAssets'
import { godotObjectTexFor } from '../godotMapLoad'

const COLOR_OBJECT = 0x8b6b3e
const TYPE_ICON: [RegExp, string][] = [
  [/stream/i, '📺'], [/phone/i, '📱'], [/fishing/i, '🎣'], [/restaurant|table/i, '🍽'], [/shop|counter/i, '🛒'],
  [/bed/i, '🛏'], [/desk/i, '🖥'], [/book/i, '📚'], [/fridge|cook|stove/i, '🧊'],
  [/bath|shower/i, '🛁'], [/toilet/i, '🚽'], [/sink/i, '🚰'], [/sofa/i, '🛋'], [/tree/i, '🌳'], [/well/i, '🪣'], [/game|console/i, '🎮'],
]

/**
 * 后端给 B16 新物品借用了旧图当占位（fridge→tree、phone→book、stream_desk/shop_counter/restaurant_table→desk、fishing_spot→well），
 * 直播画面上会误导观众，而且 tree.png 是一块白。借用的占位图一律改画带图标和名字的色块，等 E6 的正式美术。
 */
function isBorrowedSprite(obj: GameObject): boolean {
  if (!obj.sprite) return false
  const base = obj.type.toLowerCase().split('_')[0]
  const sp = obj.sprite.toLowerCase()
  return sp !== base && !obj.type.toLowerCase().startsWith(sp)
}

function tooltipLabel(obj: GameObject): string {
  const usage = `${obj.currentUsers}/${obj.maxUsers}`
  const full = obj.currentUsers >= obj.maxUsers ? ' — 使用中' : ''
  return `${obj.name} (${usage})${full}`
}

/** 地图物品：有 sprite 用图；没有就画一个带名字的圆角色块（E6 换美术前的占位） */
export default class GameObjectSprite {
  private nodes: Phaser.GameObjects.GameObject[] = []
  private tooltip: Phaser.GameObjects.Text | null = null
  private hiddenByRoof = false

  constructor(scene: Phaser.Scene, obj: GameObject) {
    const footprint = obj.tiles && obj.tiles.length > 0 ? obj.tiles : [obj.position]
    const xs = footprint.map(p => p.x)
    const ys = footprint.map(p => p.y)
    const minX = Math.min(...xs), minY = Math.min(...ys)
    const maxX = Math.max(...xs), maxY = Math.max(...ys)
    const cols = maxX - minX + 1
    const rows = maxY - minY + 1
    const { x: px, y: py } = tileToPixel(minX, minY)
    const imgW = cols * TILE_SIZE
    const imgH = rows * TILE_SIZE

    // 11-14 Godot 同步②：Godot 的物品清单（assets/ext/objects/manifest.json，48 px/格 ×2）优先——底边贴占地底边、水平居中、按底边 y 排序（同 ObjectsLayer._place）
    const g = godotObjectTexFor(scene, obj.type, minX, minY)
    if (g) {
      const k = TILE_SIZE / g.pxPerTile
      const img = scene.add.image(px + imgW / 2, py + imgH, g.key).setOrigin(0.5, 1).setScale(k).setDepth(py + imgH).setInteractive()
      this.nodes.push(img)
      const tooltip = scene.add.text(px + imgW / 2, py - 2, tooltipLabel(obj), { fontSize: '12px', color: '#ffffff', backgroundColor: '#1a1a2e', padding: { x: 4, y: 2 } }).setOrigin(0.5, 1).setDepth(10).setVisible(false)
      this.tooltip = tooltip
      img.on('pointerover', () => { if (!this.hiddenByRoof) tooltip.setVisible(true) })
      img.on('pointerout', () => tooltip.setVisible(false))
      return
    }
    // 优先自制图（按物品类型；bed_21 这类直接有同名图），其次后端给的旧图，借用占位图不用
    const aiType = aiObjectTypeFor(obj.type)
    const aiKey = aiEnabled() && scene.textures.exists(aiObjectKey(obj.type)) ? aiObjectKey(obj.type) : aiEnabled() && scene.textures.exists(aiObjectKey(aiType)) ? aiObjectKey(aiType) : null
    const genKey = aiKey ? aiKey : scene.textures.exists(objTextureKey(obj.type)) ? objTextureKey(obj.type)
      : scene.textures.exists(objTextureKey(obj.type.replace(/_\d+$/, ''))) ? objTextureKey(obj.type.replace(/_\d+$/, ''))
      : scene.textures.exists(objTextureKey(aiType)) ? objTextureKey(aiType) : null   // 像素兜底也走别名（dining_table → restaurant_table）
    const spriteKey = genKey ?? (obj.sprite && !isBorrowedSprite(obj) ? `obj_${obj.sprite}` : null)
    let hit: Phaser.GameObjects.GameObject
    if (spriteKey && scene.textures.exists(spriteKey)) {
      const img = scene.add.image(px + imgW / 2, py + imgH / 2, spriteKey).setInteractive()
      const srcTex = scene.textures.get(spriteKey).getSourceImage() as { width: number; height: number }
      const srcPortrait = srcTex.height > srcTex.width, fpLandscape = cols > rows
      if (aiKey) {
        // W8：AI 图按纹理实际尺寸 ×3 画（生成时已盖住 footprint，高物件向上长出格子），底边贴 footprint 底边；深度按底边 y 与人物排序
        const k = TILE_SIZE / (getAiManifest()?.tile_px ?? 32)
        const nw = srcTex.width * k, nh = srcTex.height * k
        if (srcPortrait && fpLandscape) { img.setAngle(-90); img.setDisplaySize(nw, nh); img.setPosition(px + imgW / 2, py + imgH / 2) }   // bed_21 借 bed 图：转 90°，居中
        else { img.setOrigin(0.5, 1).setDisplaySize(nw, nh).setPosition(px + imgW / 2, py + imgH) }
        img.setDepth(py + imgH - 1)
      } else {
        img.setDisplaySize(imgW, imgH).setDepth(1)
      }
      this.nodes.push(img)
      hit = img
    } else {
      const g = scene.add.graphics().setDepth(1)
      g.fillStyle(COLOR_OBJECT, 0.9)
      g.lineStyle(2, 0x3b2a1a, 0.8)
      g.fillRoundedRect(px + 6, py + 6, imgW - 12, imgH - 12, 10)
      g.strokeRoundedRect(px + 6, py + 6, imgW - 12, imgH - 12, 10)
      this.nodes.push(g)
      const icon = TYPE_ICON.find(([re]) => re.test(`${obj.type} ${obj.name}`))?.[1] ?? '📦'
      const label = scene.add.text(px + imgW / 2, py + imgH / 2, `${icon}\n${obj.name}`, {
        fontFamily: 'system-ui, "PingFang SC", "Microsoft YaHei", sans-serif',
        fontSize: '14px', color: '#fff7e6', align: 'center',
        stroke: '#000000', strokeThickness: 3,
      }).setOrigin(0.5).setDepth(2).setResolution(2)
      this.nodes.push(label)
      const zone = scene.add.zone(px + imgW / 2, py + imgH / 2, imgW, imgH).setInteractive()
      this.nodes.push(zone)
      hit = zone
    }

    const tooltip = scene.add
      .text(px + imgW / 2, py - 2, tooltipLabel(obj), {
        fontSize: '12px', color: '#ffffff', backgroundColor: '#1a1a2e', padding: { x: 4, y: 2 },
      })
      .setOrigin(0.5, 1)
      .setDepth(10)
      .setVisible(false)
    this.tooltip = tooltip
    hit.on('pointerover', () => { if (!this.hiddenByRoof) tooltip.setVisible(true) })
    hit.on('pointerout',  () => tooltip.setVisible(false))
  }

  /** 室内物品在屋顶视图下隐藏（W8 两套视图）；tooltip 只在悬停时显示，不受影响 */
  setVisible(v: boolean) {
    this.hiddenByRoof = !v
    for (const n of this.nodes) (n as unknown as { setVisible?: (b: boolean) => void }).setVisible?.(v)
    if (!v) this.tooltip?.setVisible(false)
  }

  destroy() {
    for (const n of this.nodes) n.destroy()
    this.tooltip?.destroy()
    this.nodes = []
  }
}
