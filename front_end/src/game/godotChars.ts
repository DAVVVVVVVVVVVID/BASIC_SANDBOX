/**
 * Godot 呈现层的六角色（主播 Q 版 h128 条带）在 Phaser 侧的纯逻辑：外观键、姿态映射、清单类型。
 * 与 whale-godot/scripts/Actor.gd 的 key_for / _refresh_anim 保持一致（11-14 总控：5173 画面同步成 Godot 的）。
 * 素材不复制进仓库：vite 的 /art 只读路由指向 whale-godot/assets/ext（见 vite.config.ts，VITE_ART_DIR 可覆盖）。
 */
export const ART_BASE = '/art'
export const GODOT_CHAR_KEYS = ['whale', 'achan', 'claudine', 'cook', 'grocer', 'fisher'] as const
export type GodotCharKey = typeof GODOT_CHAR_KEYS[number]

export interface GodotCharAnim { file: string; frames: number; fps: number; loop: boolean }
export interface GodotCharManifest {
  format: number
  images_dir: string
  frame_w: number
  frame_h: number
  anchor: [number, number]      // 脚底中心（帧内像素）
  scale: number                 // Godot 世界尺度（48 px/格）下的缩放；Phaser 96 px/格 → ×2
  display_name?: string
  animations: Record<string, GodotCharAnim>   // idle / walk / sleep / sit / eat / phone / talk
}
/** Godot 一格 48 px；Phaser 一格 96 px → 同一张图在 Phaser 里的缩放 = scale × 2 */
export const GODOT_TILE_PX = 48

export function parseGodotCharManifest(raw: unknown): GodotCharManifest | null {
  const r = raw as Record<string, unknown> | null
  if (!r || typeof r !== 'object' || !r.animations || typeof r.animations !== 'object') return null
  const fw = Number(r.frame_w), fh = Number(r.frame_h)
  if (!fw || !fh) return null
  const anc = Array.isArray(r.anchor) && r.anchor.length === 2 ? [Number(r.anchor[0]), Number(r.anchor[1])] as [number, number] : [fw / 2, fh] as [number, number]
  const animations: Record<string, GodotCharAnim> = {}
  for (const [k, v] of Object.entries(r.animations as Record<string, Record<string, unknown>>)) {
    if (!v || typeof v !== 'object') continue
    animations[k] = { file: String(v.file ?? `${k}.png`), frames: Math.max(1, Number(v.frames) || 1), fps: Number(v.fps) || 6, loop: v.loop !== false }
  }
  if (!animations.idle) return null
  return { format: Number(r.format) || 2, images_dir: String(r.images_dir ?? ''), frame_w: fw, frame_h: fh, anchor: anc, scale: Number(r.scale) || 1, display_name: typeof r.display_name === 'string' ? r.display_name : undefined, animations }
}

/** 同 Actor.gd key_for：agent_id 优先（claudine = 原小千 npc_xiaoqian），再按名字，再按控制者，最后名字哈希落到路人池 */
export function godotCharKeyFor(name: string, controller?: string | null, agentId?: string | null): GodotCharKey {
  switch (agentId ?? '') {
    case 'whale': return 'whale'
    case 'achan': return 'achan'
    case 'claudine': case 'npc_xiaoqian': return 'claudine'
    case 'npc_rest_owner': return 'cook'
    case 'npc_grocer': return 'grocer'
    case 'npc_fisher': return 'fisher'
  }
  const s = (name || '').toLowerCase()
  if (/克劳蒂娜|小克|claudine/.test(s)) return 'claudine'
  if (/鲸|whale/.test(s)) return 'whale'
  if (/阿蝉|achan|蝉/.test(s)) return 'achan'
  if (/小千|千小满|小满|xiaoqian|regular/.test(s)) return 'claudine'
  if (/杂货|grocer|店老板娘/.test(s)) return 'grocer'
  if (/餐厅|餐馆|厨|cook|chef/.test(s)) return 'cook'
  if (/渔|fish/.test(s)) return 'fisher'
  if (/店/.test(s)) return 'grocer'
  if (controller === 'human') return 'achan'
  const pool: GodotCharKey[] = ['cook', 'grocer', 'fisher']
  let h = 0
  for (const b of new TextEncoder().encode(s)) h = (h * 31 + b) % 2147483647
  return pool[h % pool.length]
}

export type GodotPose = 'sleep' | 'eat' | 'phone' | 'talk' | 'sit' | null
/** 同 Actor.gd _refresh_anim：状态文字 → 姿态动画；没有该动画就退到下一档 */
export function godotPoseFor(stateText: string | null | undefined, has: (anim: string) => boolean): GodotPose {
  const t = stateText ?? ''
  if (!t) return null
  if (t.includes('睡') && has('sleep')) return 'sleep'
  if (t.includes('吃') && has('eat')) return 'eat'
  if ((t.includes('手机') || t.includes('刷')) && has('phone')) return 'phone'
  if ((t.includes('聊') || t.includes('直播') || t.includes('说')) && has('talk')) return 'talk'
  if (/坐|吃|看|工作|直播|电脑|练琴|休息/.test(t) && has('sit')) return 'sit'
  return null
}
