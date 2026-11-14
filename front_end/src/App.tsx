import { useEffect, useRef } from 'react'
import { fetchWorld, fetchEvents, leavePlayer, setDndOnUnload } from './api/world'
import { initGame } from './game/PhaserGame'
import { startTickSystem } from './game/systems/TickSystem'
import { useGameStore } from './store/gameStore'
import InteractionPanel from './ui/InteractionPanel'
import HUD from './ui/HUD'
import WorldInfoPanel from './ui/WorldInfoPanel'
import ActionLog from './ui/ActionLog'
import TimeControlPanel from './ui/TimeControlPanel'
import Minimap from './ui/Minimap'
import JoinScreen from './ui/JoinScreen'
import ChatPanel from './ui/ChatPanel'
import ConnectionBadge from './ui/ConnectionBadge'
import QQPanel from './ui/QQPanel'
import BackpackPanel from './ui/BackpackPanel'
import KnockPanel from './ui/KnockPanel'
import SpectateApp from './spectate/SpectateApp'
import ReplayApp from './replay/ReplayApp'
import BrainApp from './brain/BrainApp'
import FlatApp from './flat/FlatApp'
import AssetsReviewApp from './review/AssetsReviewApp'
import { isSpectateRoute } from './spectate/params'
import type { Player } from './types'
import { setZoneNames } from './game/map/zones'
import { loadAiManifest } from './game/aiAssets'

/** 操控模式（作者以阿蝉身份进入） */
function PlayApp() {
  const initialized = useRef(false)
  const myPlayerId = useGameStore((s) => s.myPlayerId)

  const handleJoined = async (playerId: string, player: Player, name: string, identity?: string) => {
    if (initialized.current) return
    initialized.current = true
    const { setPlayer, setWorldState, setMap, setObjects, setMyPlayerId, setPlayers, setMode, setIdentity } = useGameStore.getState()
    setMode('play')
    setMyPlayerId(playerId)
    setIdentity(identity ?? null)
    setPlayer(player)
    try {
      const [worldData, events] = await Promise.all([fetchWorld(), fetchEvents(), loadAiManifest()])
      setWorldState(worldData.worldState)
      setZoneNames(worldData.zone_names)
      setMap(worldData.tiles, worldData.tiled, worldData.worldState?.mapVersion, { edges: worldData.edges, floors: worldData.floors, access: worldData.access, arenas: worldData.arenas, map: worldData.map })
      setObjects(worldData.objects)
      setPlayers(worldData.players ?? [])
      initGame({ mode: 'play', worldData, events, player, myPlayerId: playerId, playerName: name })
      startTickSystem(playerId, name)
    } catch (err) {
      console.error('[Init Error]', err)
      initialized.current = false
      setMyPlayerId(null)
    }
  }

  useEffect(() => {
    const onUnload = () => {
      const { myPlayerId: id, identity } = useGameStore.getState()
      if (!id) return
      if (identity === 'achan') { setDndOnUnload(id, true); return }   // 主播离开：阿蝉留在镇上、勿扰归位，不删人（§12.12）
      leavePlayer(id)
    }
    let fired = false
    const once = () => { if (fired) return; fired = true; onUnload() }
    window.addEventListener('beforeunload', once)
    window.addEventListener('pagehide', once)   // 移动端 / 后台关闭不触发 beforeunload，pagehide 兜底
    return () => { window.removeEventListener('beforeunload', once); window.removeEventListener('pagehide', once) }
  }, [])

  if (!myPlayerId) {
    return <JoinScreen onJoined={handleJoined} />
  }

  return (
    <div style={{ position: 'fixed', inset: 0, overflow: 'hidden', background: '#0f1020' }}>
      <div id="game-container" style={{ position: 'absolute', inset: 0 }} />
      <InteractionPanel />
      <HUD />
      <WorldInfoPanel />
      <ActionLog />
      <TimeControlPanel />
      <Minimap />
      <ChatPanel />
      <ConnectionBadge />
      <QQPanel playerId={myPlayerId} readOnly={false} compact style={{ top: 120, right: 16 }} />
      <BackpackPanel />
      <KnockPanel />
    </div>
  )
}

export default function App() {
  if (isSpectateRoute()) return <SpectateApp />
  if (/^\/replay\/?$/.test(window.location.pathname)) return <ReplayApp />
  if (/^\/brain\/?$/.test(window.location.pathname)) return <BrainApp />
  if (/^\/flat\/?$/.test(window.location.pathname)) return <FlatApp />
  if (/^\/assets-review\/?$/.test(window.location.pathname)) return <AssetsReviewApp />
  return <PlayApp />
}
