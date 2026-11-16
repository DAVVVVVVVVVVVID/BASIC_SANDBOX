/**
 * 操控页像素 RPG 菜单风（主播 11-16 定稿 mockC1 / C2）——配色与通用样式。
 * 素材包（九宫格 / 按钮三态 / 药丸 / 属性条 / 图标 / 气泡 / 手机 / 小地图框）到了换成 border-image / 背景图，这里先用 CSS 画出同色骨架。
 */
import type { CSSProperties } from 'react'

export const C = {
  cream: '#FFF8EC', creamA: 'rgba(255,248,236,0.92)',
  sky: '#7FB6E8', mint: '#8FD3C7', peach: '#FFB38A',
  teal: '#3BB7A8', coral: '#FF8A73', amber: '#F2B84B', lavender: '#C9B6F2',
  ink: '#3B2F2F', inkSoft: '#7A6A5A', shadow: '#D9C9B0',
  track: '#EDE3D2',
  bar: { fullness: '#F2A14B', energy: '#7CCB7A', social: '#6FA8E8', fun: '#F28BB0', mood: '#F2B84B' } as Record<string, string>,
} as const

export const FONT = '"Fusion Pixel 12px", "Zpix", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif'

/** cream 面板：2px 天蓝描边 + 1px 白内高光 + 右下暖阴影 */
export function panel(extra: CSSProperties = {}, outline: string = C.sky): CSSProperties {
  return {
    background: C.creamA, border: `2px solid ${outline}`, borderRadius: 8,
    boxShadow: `inset 0 0 0 1px rgba(255,255,255,0.9), 3px 3px 0 ${C.shadow}`,
    color: C.ink, fontFamily: FONT, fontSize: 13, lineHeight: 1.35, userSelect: 'none',
    imageRendering: 'pixelated',
    ...extra,
  }
}

/** 按钮：primary teal / secondary coral / warn amber / neutral cream；三态靴 CSS class（rpg.css） */
export function btn(kind: 'primary' | 'secondary' | 'warn' | 'neutral' | 'thought' = 'neutral', extra: CSSProperties = {}): CSSProperties {
  const bg = kind === 'primary' ? C.teal : kind === 'secondary' ? C.coral : kind === 'warn' ? C.amber : kind === 'thought' ? C.lavender : C.cream
  const fg = kind === 'neutral' || kind === 'thought' ? C.ink : '#fff'
  return {
    background: bg, color: fg, border: `2px solid ${kind === 'neutral' ? C.sky : 'rgba(0,0,0,0.18)'}`, borderRadius: 6,
    boxShadow: `inset 0 1px 0 rgba(255,255,255,0.6), 0 2px 0 ${C.shadow}`,
    padding: '4px 10px', fontFamily: FONT, fontSize: 13, cursor: 'pointer', lineHeight: 1.2,
    ...extra,
  }
}

/** 状态药丸（淡彩）：按状态文字挑色 */
export function pillColor(label: string): { bg: string; fg: string } {
  const l = label
  if (/睡/.test(l)) return { bg: '#E6DDF8', fg: '#5B4A8A' }
  if (/直播/.test(l)) return { bg: '#FFD9D4', fg: '#A33A2E' }
  if (/钓/.test(l)) return { bg: '#D8EAF9', fg: '#2F5F8A' }
  if (/打工|工作|电脑/.test(l)) return { bg: '#FBDCE8', fg: '#8A2F5A' }
  if (/做饭|吃/.test(l)) return { bg: '#FFE3CF', fg: '#8A4A1F' }
  if (/整理|买|卖|逛/.test(l)) return { bg: '#D9F2EB', fg: '#246B5C' }
  if (/走|散步|路/.test(l)) return { bg: '#FBEBC9', fg: '#7A5A14' }
  if (/聊|说/.test(l)) return { bg: '#DDE9FB', fg: '#2F4F8A' }
  if (/离线/.test(l)) return { bg: '#ECE7DF', fg: '#8A7F72' }
  return { bg: '#EDE3D2', fg: C.inkSoft }
}

/** 心情脸：按 mood 分档 */
export function moodFace(mood: number | undefined | null): string {
  if (mood == null) return '🙂'
  if (mood >= 70) return '😊'
  if (mood >= 45) return '🙂'
  if (mood >= 25) return '😐'
  return '😟'
}

export const kit = (name: string) => `assets/ui/kit/${name}.png`
export const AVATAR_KEYS = ['whale', 'achan', 'claudine', 'cook', 'grocer', 'fisher'] as const
export const avatarUrl = (key: string, px: 40 | 56 | 80 | 112 = 80) => `assets/ui/avatars/${key}_${px}.png`
