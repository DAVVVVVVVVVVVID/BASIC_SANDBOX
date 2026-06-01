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
import type { TimePeriod, Player } from './types'

const PERIOD_BG: Record<TimePeriod, string> = {
  morning: '#F5C518',
  day:     '#87CEEB',
  dusk:    '#FF6B35',
  night:   '#1A1A3E',
}

function App() {
  const initialized = useRef(false)
  const period    = useGameStore((s) => s.worldState?.period ?? 'night')
  const myPlayerId = useGameStore((s) => s.myPlayerId)
  const { setPlayer, setWorldState, setTiles, setMyPlayerId } = useGameStore.getState()

  const handleJoined = async (playerId: string, player: Player) => {
    if (initialized.current) return
    initialized.current = true

    setMyPlayerId(playerId)
    setPlayer(player)

    try {
      const [worldData, events] = await Promise.all([fetchWorld(), fetchEvents()])
      setWorldState(worldData.worldState)
      setTiles(worldData.tiles)
      initGame(worldData, player, playerId, events)
      startTickSystem(playerId)
    } catch (err) {
      console.error('[Init Error]', err)
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
    <div style={{
      position: 'relative',
      width: '100%',
      height: '100%',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: PERIOD_BG[period],
      transition: 'background-color 2s ease',
    }}>
      <div style={{ position: 'relative' }}>
        <div id="game-container" />
        <InteractionPanel />
      </div>
      <HUD />
      <WorldInfoPanel />
      <ActionLog />
      <TimeControlPanel />
      <Minimap />
      <ChatPanel />
    </div>
  )
}

export default App
