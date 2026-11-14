import Phaser from 'phaser'
import { Position, Facing, NeedVars, NEED_KEYS } from '../../types'
import { tileCenter, TILE_SIZE } from '../map/TileMap'
import { CharKey, charTextureKey, resolveCharKey, aiAnimPrefix } from '../assets'
import { aiEnabled, aiCharKey, aiCharBase, getAiManifest, AI_CHAR_FRAME } from '../aiAssets'
import { CHAR_FRAME } from '../assets'
import { godotCharKeyFor, godotPoseFor, GODOT_TILE_PX, type GodotCharManifest } from '../godotChars'
import { godotCharReady, godotCharManifest, godotCharTex, godotCharAnim } from '../godotCharsLoad'

export interface PoseAnchor { x: number; y: number; angle: number; facing?: Facing; depth: number }
export interface PoseAnchors { sleep: PoseAnchor | null; sit: PoseAnchor | null }

const SCALE = 4
const AI_DISPLAY_W = 96             // AI 角色显示宽度 = 一格（主播 11-07：跟物品一比太小 → 一格宽一格半高）
const BASE_STEP_MS = 300            // 一格基准用时（与 InputSystem 一致）
const ARROW_OFFSET = 30
const NAME_Y   = -58
const STATE_Y  = -44
const BUBBLE_Y = -82
const BAR_Y    = 34
const BAR_W    = 64
const BAR_H    = 4
const BAR_GAP  = 2
const CATCHUP_PATH = 3              // 积压超过这么多格就加速追赶

const FACING_OFFSET: Record<Facing, [number, number]> = {
  right: [ ARROW_OFFSET,  0],
  left:  [-ARROW_OFFSET,  0],
  down:  [ 0,  ARROW_OFFSET],
  up:    [ 0, -ARROW_OFFSET],
}
const ARROW_TRI: Record<Facing, [number, number, number, number, number, number]> = {
  right: [ 8,  0, -5, -5, -5,  5],
  left:  [-8,  0,  5, -5,  5,  5],
  down:  [ 0,  8, -5, -5,  5, -5],
  up:    [ 0, -8, -5,  5,  5,  5],
}

export const NEED_COLORS: Record<keyof NeedVars, number> = {
  fullness: 0xf6ad55,
  energy:   0x63b3ed,
  social:   0xb794f4,
  fun:      0x68d391,
  mood:     0xfbd38d,
}
export const NEED_LABELS: Record<keyof NeedVars, string> = {
  fullness: '饱', energy: '力', social: '社', fun: '乐', mood: '心',
}

export interface ActorOptions {
  name: string
  charKey: CharKey
  isSelf?: boolean
  showArrow?: boolean
  /** 11-14 Godot 同步：按 agent_id / 控制者选六角色外观（同 Actor.gd key_for） */
  controller?: string | null
  agentId?: string | null
}

/**
 * 场上一个人的精灵：沿路点按时间匀速移动（而不是跳格），自带名字牌、状态标签、聊天气泡、七变量小条。
 * 自己与他人共用；自己由 InputSystem 的预测驱动，他人由 /world 轮询驱动。
 */
export default class ActorSprite {
  private scene: Phaser.Scene
  private sprite: Phaser.GameObjects.Sprite
  private arrow: Phaser.GameObjects.Graphics | null = null
  private nameText: Phaser.GameObjects.Text
  private stateText: Phaser.GameObjects.Text
  private bubble: Phaser.GameObjects.Container | null = null
  private bubbleText: Phaser.GameObjects.Text | null = null
  private bubbleBg: Phaser.GameObjects.Graphics | null = null
  private bar: Phaser.GameObjects.Graphics | null = null
  /** v1.1：进食 / 下厨进度条（头顶状态标签下方一条细条） */
  private progressBar: Phaser.GameObjects.Graphics | null = null
  private progressVal: number | null = null
  private barVars: NeedVars | null = null

  private facing: Facing
  /** 逻辑上「已经到达 / 正在走向」的最后一个格 */
  private tile: Position
  private path: Position[] = []
  private moving = false
  private idleAt = 0
  private stateLabel: string | null = null
  /** 姿态：由状态标签推断（睡觉 → 躺，坐 / 休息 / 玩游戏 / 看书 → 坐） */
  private pose: 'stand' | 'sit' | 'sleep' = 'stand'
  private dimmed = false
  private uiScale = 1
  /** 回弹 / 校正路径上不用运动方向改朝向（朝向以服务器回包为准） */
  private facingLocked = false
  readonly name: string
  readonly isSelf: boolean
  private charKey: CharKey
  private hasGen: boolean
  /** 动画键前缀：像素表 = charKey；AI 表（W8）= ai_<key>，帧 32×48 ×3 = 96×144（一格宽、一格半高；像素表 16×24 ×4 = 64×96） */
  private animKey: string
  /** 头顶文字 / 气泡的纵向偏移倍数（AI 形象更高） */
  private labelMul = 1
  /** 睡觉 / 坐下时贴到物品上（床中心 / 椅子位）：像素位置 + 旋转角 + 可选朝向 + 深度；null = 站在自己格上 */
  private poseAnchors: PoseAnchors = { sleep: null, sit: null }
  private anchor: PoseAnchor | null = null
  /** 11-14：Godot 六角色条带（h128，四向共用正面不镜像，脚底锚点；清单见 godotChars.ts）；null = 旧表 */
  private godot: { key: string; m: GodotCharManifest; scale: number } | null = null
  /** 坐 / 睡 / 吃且在用物品时的排序钉（Godot _update_pin：只改排序，不挪精灵） */
  private pinDepth: number | null = null
  /** 最近一次左右朝向（主播 11-14：Godot 条带原图 = 朝左，向右走 flipX；上下 / 站立 / 姿态沿用） */
  private lastH: 'left' | 'right' = 'left'

  constructor(scene: Phaser.Scene, position: Position, facing: Facing, opts: ActorOptions) {
    this.scene  = scene
    this.facing = facing
    if (facing === 'left' || facing === 'right') this.lastH = facing
    this.tile   = { ...position }
    this.name   = opts.name
    this.isSelf = !!opts.isSelf
    this.charKey = resolveCharKey(opts.charKey)
    const gkey = godotCharKeyFor(opts.name, opts.controller, opts.agentId)
    const gm = godotCharReady(scene, gkey) ? godotCharManifest(gkey) : null
    const aiBase = aiCharBase(this.charKey)
    const aiTex = aiCharKey(aiBase)
    const useAi = !gm && aiEnabled() && !!getAiManifest()?.chars.includes(aiBase) && scene.textures.exists(aiTex)
    this.hasGen = !!gm || useAi || scene.textures.exists(charTextureKey(this.charKey))
    this.animKey = gm ? `gchar_${gkey}` : useAi ? aiAnimPrefix(aiBase) : this.charKey
    const afh = (getAiManifest()?.char_frame ?? [AI_CHAR_FRAME.w, AI_CHAR_FRAME.h])[1]
    const afw = (getAiManifest()?.char_frame ?? [AI_CHAR_FRAME.w, AI_CHAR_FRAME.h])[0]
    // Godot 条带：Godot 48 px/格 × scale → 这里 96 px/格，同比 ×2（h128 ×0.5 → 1:1，约 1.3 格高，与 Godot 画面一致）
    const scale = gm ? gm.scale * (TILE_SIZE / GODOT_TILE_PX) : useAi ? AI_DISPLAY_W / afw : SCALE          // AI 表：不管帧多大，显示成一格宽（96 px）
    this.labelMul = useAi ? (afh * scale) / (CHAR_FRAME.h * SCALE) : 1
    if (gm) this.godot = { key: gkey, m: gm, scale }

    const { x, y } = tileCenter(position.x, position.y)
    this.sprite = scene.add.sprite(x, y, gm ? godotCharTex(gkey, 'idle') : useAi ? aiTex : this.hasGen ? charTextureKey(this.charKey) : 'player_idle')
      .setScale(scale)
      .setOrigin(0.5, 0.5)
      .setDepth(y)
    // Godot：节点在格底 −4（(y+1)·T − 4），精灵以脚底锚点挂上去；这里精灵逻辑位置仍是格中心，用 origin 把脚底放到格底 −4
    if (gm) this.sprite.setOrigin(gm.anchor[0] / gm.frame_w, (gm.anchor[1] - (TILE_SIZE / 2 - 4) / scale) / gm.frame_h)
    this.playAnim(false)

    if (opts.showArrow) {
      this.arrow = scene.add.graphics().setDepth(y + 1)
      this.redrawArrow()
    }

    this.nameText = scene.add.text(x, y + NAME_Y, opts.name, {
      fontFamily: 'system-ui, "PingFang SC", "Microsoft YaHei", sans-serif',
      fontSize: '14px',
      color: this.isSelf ? '#ffe9a8' : '#ffffff',
      stroke: '#000000', strokeThickness: 4,
    }).setOrigin(0.5, 1).setDepth(y + 2).setResolution(2)

    this.stateText = scene.add.text(x, y + STATE_Y, '', {
      fontFamily: 'system-ui, "PingFang SC", "Microsoft YaHei", sans-serif',
      fontSize: '12px',
      color: '#c3dafe',
      stroke: '#000000', strokeThickness: 3,
    }).setOrigin(0.5, 1).setDepth(y + 2).setResolution(2).setVisible(false)
  }

  // ── 位置与移动 ───────────────────────────────────────────────────────────────

  getTile(): Position { return { ...this.tile } }
  getPixelPosition() { return { x: this.sprite.x, y: this.sprite.y } }
  getFacing() { return this.facing }
  /** 路径终点（没有路径时就是当前格） */
  getPathEnd(): Position { return this.path.length ? { ...this.path[this.path.length - 1] } : { ...this.tile } }
  isMoving() { return this.moving }
  /** 像素点是否落在精灵身上（自由镜头点人跟随） */
  containsPoint(x: number, y: number) { return this.sprite.visible && Phaser.Geom.Rectangle.Contains(this.sprite.getBounds(), x, y) }
  /** W9 任务 0b：服务器说它在 walking（逐格推进）→ 路点空档也保持走路帧，不闪回待机 */
  private serverWalking = false
  setServerWalking(w: boolean) {
    if (w === this.serverWalking) return
    this.serverWalking = w
    if (!w && this.path.length === 0 && this.moving) { this.setMoving(false); this.idleAt = 0 }
    // 走 ↔ 停 切换时重算姿势：开始走立刻起身（解除贴床 / 贴椅、换走路 / 站立帧），停下再按标签摆姿
    if (!this.moving) { this.playAnim(false); this.applyPoseAnchor() }
  }
  /** 遮挡判定用（Godot OccluderFade）：精灵世界矩形（脚底在 footY，向上 anchor 高、宽 frame_w × scale）与排序 y */
  occluderProbe(): { rect: Phaser.Geom.Rectangle; sortY: number } | null {
    if (!this.godot || !this.sprite.visible) return null
    const foot = this.sprite.y + TILE_SIZE / 2 - 4
    const w = this.godot.m.frame_w * this.godot.scale, h = this.godot.m.anchor[1] * this.godot.scale
    return { rect: new Phaser.Geom.Rectangle(this.sprite.x - w / 2, foot - h, w, h), sortY: this.pinDepth ?? foot }
  }
  /** 调试：当前标签 / 姿势 / 是否贴在物品上 */
  debugPose() { return { label: this.stateLabel, pose: this.pose, anchored: this.anchored, serverWalking: this.serverWalking } }
  /** 每格用时（ms）：人类键盘 300；agent 按服务器 1 格 / 游戏秒 × 镇倍速 */
  private stepMs = BASE_STEP_MS
  setStepMs(ms: number) { this.stepMs = Math.max(60, ms) }

  /** 追加一个相邻路点（预测步 / 轮询差分） */
  pushWaypoint(p: Position) {
    const end = this.getPathEnd()
    if (end.x === p.x && end.y === p.y) return
    this.path.push({ ...p })
  }

  /** 用新路径替换（校正 / 回弹）：从当前像素位置平滑走到路径上 */
  setPath(points: Position[], lockFacing = false) {
    this.path = points.map(p => ({ ...p }))
    this.facingLocked = lockFacing && this.path.length > 0
    if (this.path.length === 0) return
    // 如果第一个点就是当前格而我们正站在格中心，丢掉它
    const first = this.path[0]
    const c = tileCenter(first.x, first.y)
    if (Math.abs(c.x - this.sprite.x) < 0.5 && Math.abs(c.y - this.sprite.y) < 0.5) {
      this.tile = { ...first }
      this.path.shift()
    }
  }

  /** 直接瞬移 */
  snapTo(p: Position, facing?: Facing) {
    this.path = []
    this.facingLocked = false
    if (this.anchored) { this.anchored = false; this.anchor = null; this.sprite.setAngle(0) }
    this.tile = { ...p }
    const c = tileCenter(p.x, p.y)
    this.sprite.setPosition(c.x, c.y)
    if (facing) this.setFacing(facing)
    this.setMoving(false)
    this.layout()
  }

  setFacing(facing: Facing) {
    if (this.anchored && this.anchor?.facing) return   // 坐在椅子上：朝向由椅子决定，不跟服务器朝向
    if (this.facing === facing) return
    this.facing = facing
    if (facing === 'left' || facing === 'right') this.lastH = facing
    this.playAnim(this.moving)
    this.redrawArrow()
  }

  /** 自制四向表：<key>_walk_<dir> / <key>_idle_<dir>；没有自制表时退回旧的 walk / idle + 翻转 */
  private playAnim(moving: boolean) {
    if (this.godot) {
      // 同 Actor.gd _refresh_anim：走 → walk；停 → 按状态文字挑姿态（睡 / 吃 / 手机 / 聊 / 坐），否则 idle；四向共用正面不镜像
      const g = this.godot
      const has = (a: string) => this.scene.anims.exists(godotCharAnim(g.key, a))
      const posed = !moving && !this.serverWalking
      const pose = posed ? godotPoseFor(this.stateLabel, has) : null
      const anim = moving ? (has('walk') ? 'walk' : 'idle') : pose ?? 'idle'
      this.sprite.setFlipX(this.lastH === 'right')   // 只翻精灵（origin 在水平中心，标签 / 排序不受影响）
      this.sprite.play(godotCharAnim(g.key, anim), true)
      return
    }
    if (this.hasGen) {
      this.sprite.setFlipX(false)
      const posed = !moving && !this.serverWalking   // 总控 11-08：服务器说在走（两步之间精灵可能短暂静止）就不摆睡 / 坐姿
      if (posed && this.pose === 'sleep') { this.sprite.play(`${this.animKey}_sleep`, true); return }
      if (posed && this.pose === 'sit') { this.sprite.play(`${this.animKey}_sit_${this.facing}`, true); return }
      this.sprite.play(`${this.animKey}_${moving ? 'walk' : 'idle'}_${this.facing}`, true)
    } else {
      this.sprite.setFlipX(this.facing === 'left')
      this.sprite.play(moving ? 'walk' : 'idle', true)
    }
  }

  private setMoving(m: boolean) {
    if (m === this.moving) return
    this.moving = m
    if (m && this.anchored) { this.anchored = false; this.anchor = null; this.sprite.setAngle(0) }   // 起身走人：解除贴床 / 贴椅
    this.playAnim(m)
    if (!m) this.applyPoseAnchor()
  }

  /** 每帧调用。speedMul = 玩家 moveSpeed（1.0 = 300 ms/格） */
  update(_time: number, dt: number, speedMul = 1) {
    if (this.path.length > 0) {
      const target = this.path[0]
      const c = tileCenter(target.x, target.y)
      // 面朝方向跟随路点
      const dx = c.x - this.sprite.x
      const dy = c.y - this.sprite.y
      if (!this.facingLocked) {
        if (Math.abs(dx) > Math.abs(dy)) this.setFacing(dx > 0 ? 'right' : 'left')
        else if (Math.abs(dy) > 0.5) this.setFacing(dy > 0 ? 'down' : 'up')
      }

      const catchup = this.path.length > CATCHUP_PATH ? Math.min(4, this.path.length / CATCHUP_PATH) : 1
      const pxPerMs = (TILE_SIZE / this.stepMs) * Math.max(0.1, speedMul) * catchup
      let budget = pxPerMs * dt
      const dist = Math.hypot(dx, dy)
      if (dist <= budget) {
        this.sprite.setPosition(c.x, c.y)
        this.tile = { ...target }
        this.path.shift()
        budget -= dist
        // 余量继续走下一段，保证连续移动时速度恒定
        if (this.path.length > 0 && budget > 0) {
          const n = this.path[0]
          const nc = tileCenter(n.x, n.y)
          const ndx = nc.x - c.x, ndy = nc.y - c.y
          const nd = Math.hypot(ndx, ndy) || 1
          const step = Math.min(nd, budget)
          this.sprite.setPosition(c.x + ndx / nd * step, c.y + ndy / nd * step)
        }
      } else {
        this.sprite.setPosition(this.sprite.x + dx / dist * budget, this.sprite.y + dy / dist * budget)
      }
      this.setMoving(true)
      this.idleAt = 0
    } else if (this.moving) {
      this.facingLocked = false
      // 短暂滞后再切 idle，避免连走时帧间抖动；服务器仍在 walking 时等下一格（最多 1.5 s）
      const grace = this.serverWalking ? 1500 : 90
      if (this.idleAt === 0) this.idleAt = _time + grace
      else if (_time >= this.idleAt) { this.setMoving(false); this.idleAt = 0 }
    }
    this.layout()
  }

  private layout() {
    const x = this.sprite.x, y = this.sprite.y
    if (this.godot) {
      // Godot 口径：排序 y = 脚底（格底 −4）；坐 / 睡 / 吃且在用物品 → 钉到物品底边 +1（椅背别盖住人）
      const foot = y + TILE_SIZE / 2 - 4
      const head = foot - this.godot.m.anchor[1] * this.godot.scale
      const d = this.pinDepth ?? foot
      this.sprite.setDepth(d)
      if (this.arrow) { this.arrow.setDepth(d + 1); this.redrawArrow() }
      const u = this.uiScale
      this.nameText.setPosition(x, head - 10 * u).setDepth(d + 2)
      this.stateText.setPosition(x, head + 4 * u).setDepth(d + 2)
      if (this.bubble) this.bubble.setPosition(x, head - 34 * u).setDepth(d + 3)
      if (this.bar) this.bar.setPosition(x - BAR_W / 2 * u, foot - 14 * u).setDepth(d + 2)
      if (this.progressBar) this.progressBar.setPosition(x - 28 * u, head + 20 * u).setDepth(d + 2).setScale(u)
      return
    }
    // 深度按脚底 y 与物品（底边 y）排序：站在高物件后面会被挡住；贴在床 / 椅上时用物品底边 + 1，保证画在物品之上
    const d = this.anchored && this.anchor ? this.anchor.depth : y + this.sprite.displayHeight / 2 - 4
    this.sprite.setDepth(d)
    if (this.arrow) { this.arrow.setDepth(d + 1); this.redrawArrow() }
    const u = this.uiScale, v = this.uiScale * this.labelMul
    this.nameText.setPosition(x, y + NAME_Y * v).setDepth(d + 2)
    this.stateText.setPosition(x, y + STATE_Y * v).setDepth(d + 2)
    if (this.bubble) this.bubble.setPosition(x, y + BUBBLE_Y * v).setDepth(d + 3)
    if (this.bar) this.bar.setPosition(x - BAR_W / 2 * u, y + BAR_Y * v).setDepth(d + 2)
    if (this.progressBar) this.progressBar.setPosition(x - 28 * u, y + (STATE_Y + 16) * v).setDepth(d + 2).setScale(u)
  }

  /** v1.1：0–1 画进度；null 撤掉 */
  setProgress(p: number | null) {
    if (p === null) { if (this.progressBar) { this.progressBar.destroy(); this.progressBar = null } this.progressVal = null; return }
    if (this.progressVal !== null && Math.abs(this.progressVal - p) < 0.01) return
    this.progressVal = p
    if (!this.progressBar) this.progressBar = this.scene.add.graphics()
    const g = this.progressBar; g.clear()
    g.fillStyle(0x1a202c, 0.85).fillRoundedRect(0, 0, 56, 6, 3)
    g.fillStyle(0x68d391, 1).fillRoundedRect(1, 1, Math.max(2, 54 * Math.max(0, Math.min(1, p))), 4, 2)
    this.layout()
  }

  private redrawArrow() {
    if (!this.arrow) return
    const cx = this.sprite.x, cy = this.sprite.y
    const [ox, oy] = FACING_OFFSET[this.facing]
    const ax = cx + ox, ay = cy + oy
    const [x1, y1, x2, y2, x3, y3] = ARROW_TRI[this.facing]
    this.arrow.clear()
    this.arrow.fillStyle(0xffffff, 0.9)
    this.arrow.lineStyle(1.5, 0x333333, 1)
    this.arrow.fillTriangle(ax + x1, ay + y1, ax + x2, ay + y2, ax + x3, ay + y3)
    this.arrow.strokeTriangle(ax + x1, ay + y1, ax + x2, ay + y2, ax + x3, ay + y3)
  }

  // ── 叠加层 ───────────────────────────────────────────────────────────────────

  /** 相机 zoom 的倒数：让名字牌 / 气泡 / 小条在屏幕上保持同样大小 */
  setUiScale(s: number) {
    if (Math.abs(s - this.uiScale) < 1e-3) return
    this.uiScale = s
    this.nameText.setScale(s)
    this.stateText.setScale(s)
    this.bubble?.setScale(s)
    this.bar?.setScale(s)
    this.layout()
  }

  setStateLabel(label: string | null) {
    if (label === this.stateLabel) return
    this.stateLabel = label
    if (label) this.stateText.setText(label).setVisible(true)
    else this.stateText.setVisible(false)
    const pose: typeof this.pose = !label ? 'stand' : /睡|sleep|躺/.test(label) ? 'sleep' : /坐|休息|玩游戏|看书|读|吃|用餐|钓|工作|直播|刷手机|sit|rest|gam/.test(label) ? 'sit' : 'stand'
    if (pose !== this.pose) { this.pose = pose; if (!this.moving) this.playAnim(false); this.applyPoseAnchor() }
    else if (this.godot && !this.moving) this.playAnim(false)   // 同档不同姿（聊 → 刷手机）也要换条带
  }

  /** W8：睡觉 / 坐下时把人画到物品上（后端把使用者放在物品旁一格；AI 形象物品和人是两张图，不贴会像睡在地板上 / 坐在空地）。只对 AI 表生效：像素表的睡觉帧自带床 */
  setPoseAnchors(a: PoseAnchors) {
    const same = (x: PoseAnchor | null, y: PoseAnchor | null) => (!x && !y) || (!!x && !!y && x.x === y.x && x.y === y.y && x.angle === y.angle && x.facing === y.facing && x.depth === y.depth)
    if (same(a.sleep, this.poseAnchors.sleep) && same(a.sit, this.poseAnchors.sit)) return
    this.poseAnchors = a
    this.applyPoseAnchor()
  }

  private anchored = false
  private applyPoseAnchor() {
    const a = this.pose === 'sleep' ? this.poseAnchors.sleep : this.pose === 'sit' ? this.poseAnchors.sit : null
    if (this.godot) {
      // Godot 口径：人不挪到物品上，只把排序 y 钉到所用物品底边 +1（_update_pin）
      const pin = a && !this.moving && !this.serverWalking ? a.depth : null
      if (pin !== this.pinDepth) { this.pinDepth = pin; this.layout() }
      return
    }
    const want = !!a && !this.moving && !this.serverWalking && this.animKey.startsWith('ai_')
    if (want && a) {
      this.anchor = a
      this.sprite.setPosition(a.x, a.y).setAngle(a.angle)
      if (a.facing && a.facing !== this.facing) { this.facing = a.facing; this.playAnim(false); this.redrawArrow() }
      this.anchored = true
      this.layout()
    } else if (this.anchored) {
      this.anchored = false; this.anchor = null
      this.sprite.setAngle(0)
      if (!this.moving) { const c = tileCenter(this.tile.x, this.tile.y); this.sprite.setPosition(c.x, c.y) }
      this.layout()
    }
  }

  private hidden = false
  /** 被屋顶挡住（W8 小镇视角房屋不镂空） */
  setHidden(h: boolean) {
    if (h === this.hidden) return
    this.hidden = h
    const v = !h
    this.sprite.setVisible(v); this.nameText.setVisible(v); this.stateText.setVisible(v && !!this.stateLabel)
    this.arrow?.setVisible(v); this.bubble?.setVisible(v); this.bar?.setVisible(v)
  }

  /** 离线（agent 进程挂了但身体还在）→ 半透明 */
  setDimmed(dim: boolean) {
    if (dim === this.dimmed) return
    this.dimmed = dim
    const a = dim ? 0.45 : 1
    this.sprite.setAlpha(a)
    this.nameText.setAlpha(a)
    this.stateText.setAlpha(a)
    this.bar?.setAlpha(a)
  }

  setBubble(text: string | null) {
    if (!text) {
      if (this.bubble) { this.bubble.destroy(true); this.bubble = null; this.bubbleText = null; this.bubbleBg = null }
      return
    }
    if (this.bubble && this.bubbleText && this.bubbleText.text === text) return
    if (!this.bubble) {
      this.bubbleBg = this.scene.add.graphics()
      this.bubbleText = this.scene.add.text(0, 0, '', {
        fontFamily: 'system-ui, "PingFang SC", "Microsoft YaHei", sans-serif',
        fontSize: '13px',
        color: '#1a202c',
        wordWrap: { width: 220, useAdvancedWrap: true },
        align: 'left',
      }).setOrigin(0.5, 1).setResolution(2)
      this.bubble = this.scene.add.container(this.sprite.x, this.sprite.y + BUBBLE_Y, [this.bubbleBg, this.bubbleText]).setScale(this.uiScale)
    }
    const t = this.bubbleText!
    t.setText(text)
    const padX = 8, padY = 5
    const w = t.width + padX * 2
    const h = t.height + padY * 2
    const g = this.bubbleBg!
    g.clear()
    g.fillStyle(0xffffff, 0.95)
    g.lineStyle(1, 0x2d3748, 0.6)
    g.fillRoundedRect(-w / 2, -h - 8, w, h, 6)
    g.strokeRoundedRect(-w / 2, -h - 8, w, h, 6)
    g.fillTriangle(-6, -8, 6, -8, 0, 0)
    t.setPosition(0, -8 - padY)
    this.bubble.setAlpha(1)
    this.layout()
  }

  /** 七变量小图标条（null 隐藏） */
  setVars(vars: NeedVars | null) {
    if (!vars) {
      if (this.bar) { this.bar.destroy(); this.bar = null }
      this.barVars = null
      return
    }
    if (this.barVars && NEED_KEYS.every(k => Math.abs(this.barVars![k] - vars[k]) < 0.5)) return
    this.barVars = { ...vars }
    if (!this.bar) this.bar = this.scene.add.graphics().setScale(this.uiScale)
    const g = this.bar
    g.clear()
    const totalH = NEED_KEYS.length * (BAR_H + BAR_GAP) + 2
    g.fillStyle(0x000000, 0.55)
    g.fillRoundedRect(-2, -2, BAR_W + 4, totalH + 2, 3)
    NEED_KEYS.forEach((k, i) => {
      const y = i * (BAR_H + BAR_GAP)
      const v = Math.max(0, Math.min(100, vars[k] ?? 0)) / 100
      g.fillStyle(0x2d3748, 1)
      g.fillRect(0, y, BAR_W, BAR_H)
      g.fillStyle(v < 0.25 ? 0xe53e3e : NEED_COLORS[k], 1)
      g.fillRect(0, y, Math.round(BAR_W * v), BAR_H)
    })
    this.layout()
  }

  destroy() {
    this.sprite.destroy()
    this.arrow?.destroy()
    this.nameText.destroy()
    this.stateText.destroy()
    this.progressBar?.destroy()
    this.bubble?.destroy(true)
    this.bar?.destroy()
  }
}
