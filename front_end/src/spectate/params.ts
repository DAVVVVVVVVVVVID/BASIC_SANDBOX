/** `/spectate?follow=<name|id|agent_id>&hud=0&clock=1&zoom=0.667&bg=transparent&stats=1&bars=target` */
export interface SpectateParams {
  follow: string | null
  hud: boolean          // React 面板（默认 1；OBS 用 0）
  clock: boolean        // 画布内时钟（默认 1）
  zoom: number | null   // 跟随镜头 zoom（默认 2/3 → 64 px/格 = 4× 源像素）
  bg: 'dark' | 'transparent'
  stats: boolean        // 画布内帧率
  bars: 'target' | 'all' | 'none'
}

export function parseSpectateParams(search = window.location.search): SpectateParams {
  const q = new URLSearchParams(search)
  const flag = (k: string, def: boolean) => {
    const v = q.get(k)
    if (v === null) return def
    return !(v === '0' || v === 'false' || v === 'no')
  }
  const zoomRaw = q.get('zoom')
  const zoom = zoomRaw !== null && !Number.isNaN(Number(zoomRaw)) && Number(zoomRaw) > 0 ? Number(zoomRaw) : null
  const bars = q.get('bars')
  return {
    follow: q.get('follow') || null,
    hud:    flag('hud', true),
    clock:  flag('clock', true),
    zoom,
    bg:     q.get('bg') === 'transparent' ? 'transparent' : 'dark',
    stats:  flag('stats', false),
    bars:   bars === 'all' || bars === 'none' ? bars : 'target',
  }
}

export function isSpectateRoute(pathname = window.location.pathname): boolean {
  return /^\/spectate\/?$/.test(pathname)
}
