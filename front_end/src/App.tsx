import { useEffect, useRef } from 'react'
import { fetchWorld, fetchEvents, leavePlayer } from './api/world'
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
import SpectateApp from './spectate/SpectateApp'
import ReplayApp from './replay/ReplayApp'
import BrainApp from './brain/BrainApp'
import { isSpectateRoute } from './spectate/params'
import type { Player } from './types'

/** 操控模式（作者以阿蝉身份进入） */
function PlayApp() {
  const initialized = useRef(false)
  const myPlayerId = useGameStore((s) => s.myPlayerId)

  const handleJoined = async (playerId: string, player: Player, name: string) => {
    if (initialized.current) return
    initialized.current = true
    const { setPlayer, setWorldState, setMap, setObjects, setMyPlayerId, setPlayers, setMode } = useGameStore.getState()
    setMode('play')
    setMyPlayerId(playerId)
    setPlayer(player)
    try {
      const [worldData, events] = await Promise.all([fetchWorld(), fetchEvents()])
      setWorldState(worldData.worldState)
      setMap(worldData.tiles, worldData.tiled, worldData.worldState?.mapVersion, { edges: worldData.edges, floors: worldData.floors, access: worldData.access, arenas: worldData.arenas })
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
      const id = useGameStore.getState().myPlayerId
      if (id) leavePlayer(id)
    }
    window.addEventListener('beforeunload', onUnload)
    return () => window.removeEventListener('beforeunload', onUnload)
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
    </div>
  )
}

export default function App() {
  if (isSpectateRoute()) return <SpectateApp />
  if (/^\/replay\/?$/.test(window.location.pathname)) return <ReplayApp />
  if (/^\/brain\/?$/.test(window.location.pathname)) return <BrainApp />
  return <PlayApp />
}
