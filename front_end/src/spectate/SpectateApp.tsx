import { useEffect, useRef, useState } from 'react'
import Phaser from 'phaser'
import { fetchWorld, fetchEvents } from '../api/world'
import { initGame } from '../game/PhaserGame'
import type GameScene from '../game/scenes/GameScene'
import { startSpectateTick } from '../game/systems/TickSystem'
import { useGameStore } from '../store/gameStore'
import { parseSpectateParams } from './params'
import { setArtVersion } from '../game/assets'
import { setZoneNames } from '../game/map/zones'
import WorldInfoPanel from '../ui/WorldInfoPanel'
import SpectateHud from './SpectateHud'

/**
 * 旁观模式 `/spectate?follow=<name|id|agent_id>&hud=0`：
 * 不 join、不弹登录框、只发 GET；画布 1920×1080 FIT 居中；后端重启时轮询自己恢复，不白屏。
 */
export default function SpectateApp() {
  const params = useRef(parseSpectateParams()).current
  const gameRef = useRef<Phaser.Game | null>(null)
  const [phase, setPhase] = useState<'connecting' | 'running'>('connecting')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const store = useGameStore.getState()
    store.setMode('spectate')
    setArtVersion(params.art)
    if (params.bg === 'transparent') {
      document.documentElement.style.background = 'transparent'
      document.body.style.background = 'transparent'
      const root = document.getElementById('root'); if (root) root.style.background = 'transparent'
    }

    let cancelled = false
    let stopTick: (() => void) | null = null

    const boot = async () => {
      // 一直重试直到后端可达
      for (let i = 0; !cancelled; i++) {
        try {
          const [worldData, events] = await Promise.all([fetchWorld(), fetchEvents()])
          if (cancelled) return
          const s = useGameStore.getState()
          s.setWorldState(worldData.worldState)
          setZoneNames(worldData.zone_names)
          s.setMap(worldData.tiles, worldData.tiled, worldData.worldState?.mapVersion, { edges: worldData.edges, floors: worldData.floors, access: worldData.access, arenas: worldData.arenas, map: worldData.map })
          s.setObjects(worldData.objects)
          s.setPlayers(worldData.players ?? [])
          s.setConnection('online')
          gameRef.current = initGame({ mode: 'spectate', worldData, events, spectate: params })
          const game = gameRef.current
          const getTargetIds = () => {
            const scene = game.scene.getScene('GameScene') as GameScene | null
            return scene?.getVarTargetIds?.() ?? []
          }
          stopTick = startSpectateTick(getTargetIds).stop
          setPhase('running')
          return
        } catch (err) {
          if (cancelled) return
          useGameStore.getState().setConnection('offline')
          setAttempt(i + 1)
          if (i === 0) console.warn('[Spectate] backend unreachable, retrying…', err)
          await new Promise(r => setTimeout(r, Math.min(5000, 1000 * (i + 1))))
        }
      }
    }
    boot()

    return () => {
      // StrictMode 在 dev 下会 mount→cleanup→mount：这里真正收干净，第二次 mount 重新 boot
      cancelled = true
      stopTick?.()
      stopTick = null
      gameRef.current?.destroy(true)
      gameRef.current = null
    }
  }, [params])

  const transparent = params.bg === 'transparent'
  return (
    <div style={{
      position: 'fixed', inset: 0, overflow: 'hidden',
      background: transparent ? 'transparent' : '#0f1020',
    }}>
      <div id="game-container" style={{ position: 'absolute', inset: 0 }} />
      {phase === 'connecting' && params.hud && (
        <div style={{
          position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#a0aec0', fontFamily: 'system-ui, sans-serif', fontSize: 16,
        }}>
          正在连接后端…{attempt > 0 ? `（第 ${attempt} 次重试）` : ''}
        </div>
      )}
      {params.hud && phase === 'running' && (
        <>
          <WorldInfoPanel />
          <SpectateHud follow={params.follow} />
        </>
      )}
    </div>
  )
}
