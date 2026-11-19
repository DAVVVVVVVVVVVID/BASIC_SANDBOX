import { useEffect, useState } from 'react'

/**
 * 操控页手机适配（总控 mobile.md 11-16）：判定 (pointer: coarse) 且视口短边 ≤ 820 → 手机模式；`?m=1` / `?m=0` 强制。只做竖屏，横屏遮罩提示。
 */
export function isMobileNow(): boolean {
  const q = new URLSearchParams(window.location.search).get('m')
  if (q === '1') return true
  if (q === '0') return false
  const coarse = window.matchMedia?.('(pointer: coarse)').matches ?? false
  return coarse && Math.min(window.innerWidth, window.innerHeight) <= 820
}
/** 可见区域（visualViewport）：iOS 弹键盘时会把页面上推，手机外壳 / QQ 全屏直接贴到这块，不再另外按键盘高度抬（11-19 主播：QQ 进会话整页白屏） */
export interface VisualBox { top: number; h: number }
const vvBox = (): VisualBox => { const vv = window.visualViewport; return vv ? { top: Math.max(0, vv.offsetTop), h: vv.height } : { top: 0, h: window.innerHeight } }
export function useMobile(): { mobile: boolean; portrait: boolean; kb: number; vv: VisualBox } {
  const [s, setS] = useState(() => ({ mobile: isMobileNow(), portrait: window.innerHeight >= window.innerWidth, kb: 0, vv: vvBox() }))
  useEffect(() => {
    const on = () => {
      const vv = window.visualViewport
      const kb = vv ? Math.max(0, window.innerHeight - vv.height - vv.offsetTop) : 0   // 软键盘占高：聊天 / QQ 输入框跟着抬
      setS({ mobile: isMobileNow(), portrait: window.innerHeight >= window.innerWidth, kb, vv: vvBox() })
    }
    window.addEventListener('resize', on); window.addEventListener('orientationchange', on)
    window.visualViewport?.addEventListener('resize', on); window.visualViewport?.addEventListener('scroll', on)
    return () => { window.removeEventListener('resize', on); window.removeEventListener('orientationchange', on); window.visualViewport?.removeEventListener('resize', on); window.visualViewport?.removeEventListener('scroll', on) }
  }, [])
  return s
}

/** iOS Safari 无视 maximum-scale，自己吃掉双指去缩放整页 → 游戏画布收不到双指（11-19 跟随时双指缩放无效）。拦下 iOS 专有的 gesture* 事件；画布另设 touch-action: none */
let gestureBlocked = false
export function blockPageZoom() {
  if (gestureBlocked || typeof document === 'undefined') return
  gestureBlocked = true
  const stop = (e: Event) => e.preventDefault()
  for (const t of ['gesturestart', 'gesturechange', 'gestureend']) document.addEventListener(t, stop, { passive: false })
}
/** 触屏设备上输入框不自动聚焦（一聚焦 iOS 就弹键盘并上推页面） */
export const autoFocusOk = () => !(window.matchMedia?.('(pointer: coarse)').matches ?? false)
