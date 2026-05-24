import { useEffect, useRef } from 'react'
import { fetchWorld, fetchPlayer, fetchEvents } from './api/world'
import { initGame } from './game/PhaserGame'
import { startTickSystem } from './game/systems/TickSystem'
import { useGameStore } from './store/gameStore'
import InteractionPanel from './ui/InteractionPanel'
import HUD from './ui/HUD'
import WorldInfoPanel from './ui/WorldInfoPanel'
import ActionLog from './ui/ActionLog'
import TimeControlPanel from './ui/TimeControlPanel'
import Minimap from './ui/Minimap'
import type { TimePeriod } from './types'

const PERIOD_BG: Record<TimePeriod, string> = {
  morning: '#F5C518',
  day:     '#87CEEB',
  dusk:    '#FF6B35',
  night:   '#1A1A3E',
}

function App() {
  const initialized = useRef(false)
  const period = useGameStore((s) => s.worldState?.period ?? 'night')

  useEffect(() => {
    if (initialized.current) return
    initialized.current = true

    Promise.all([fetchWorld(), fetchPlayer(), fetchEvents()])
      .then(([worldData, player, events]) => {
        console.log('[World Data]', worldData)
        console.log('[Player Data]', player)

        const { setPlayer, setWorldState, setTiles } = useGameStore.getState()
        setPlayer(player)
        setWorldState(worldData.worldState)
        setTiles(worldData.tiles)

        initGame(worldData, player, events)
        startTickSystem()
      })
      .catch((err) => {
        console.error('[Init Error]', err)
      })
  }, [])

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
    </div>
  )
}

export default App
