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
export function useMobile(): { mobile: boolean; portrait: boolean; kb: number } {
  const [s, setS] = useState(() => ({ mobile: isMobileNow(), portrait: window.innerHeight >= window.innerWidth, kb: 0 }))
  useEffect(() => {
    const on = () => {
      const vv = window.visualViewport
      const kb = vv ? Math.max(0, window.innerHeight - vv.height - vv.offsetTop) : 0   // 软键盘占高：聊天 / QQ 输入框跟着抬
      setS({ mobile: isMobileNow(), portrait: window.innerHeight >= window.innerWidth, kb })
    }
    window.addEventListener('resize', on); window.addEventListener('orientationchange', on)
    window.visualViewport?.addEventListener('resize', on)
    return () => { window.removeEventListener('resize', on); window.removeEventListener('orientationchange', on); window.visualViewport?.removeEventListener('resize', on) }
  }, [])
  return s
}
