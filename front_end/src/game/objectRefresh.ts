import { useEffect } from 'react'
import { apiGet } from '../api/client'
import { useGameStore } from '../store/gameStore'
import type { GameObject } from '../types'

/**
 * 11-19 主播：买了小礼物后货架剩余数量不变——ws patch 的 objects 只带 {id, currentUsers, userList, open}，
 * 库存 shop[] / stock / listings / warehouse / menu / orders / 冰箱 contents / 灶台 cooking 都不推，ws 模式下只在连上时拿一次。
 * 这里在需要的面板打开期间按间隔补拉 GET /world?fields=objects（约 70 KB），并在买卖等动作后立即补拉一次。
 */
let inflight: Promise<void> | null = null
export function refreshObjects(): Promise<void> {
  if (inflight) return inflight
  inflight = apiGet<{ objects?: GameObject[] }>('/world?fields=objects')
    .then(r => { if (Array.isArray(r.objects) && r.objects.length) useGameStore.getState().patchObjects(r.objects) })
    .catch(() => { /* 下次再试 */ })
    .finally(() => { inflight = null })
  return inflight
}
/** 面板打开期间每 intervalMs 补拉一次（打开时立刻拉一次） */
export function useObjectRefresh(intervalMs = 4000, on = true) {
  useEffect(() => {
    if (!on) return
    void refreshObjects()
    const t = window.setInterval(() => { void refreshObjects() }, intervalMs)
    return () => window.clearInterval(t)
  }, [intervalMs, on])
}
