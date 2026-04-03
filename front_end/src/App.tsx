import { useEffect, useRef } from 'react'
import { fetchWorld, fetchPlayer, fetchEvents } from './api/world'
import { initGame } from './game/PhaserGame'
import { startTickSystem } from './game/systems/TickSystem'
import { useGameStore } from './store/gameStore'
import InteractionPanel from './ui/InteractionPanel'
import HUD from './ui/HUD'
import WorldInfoPanel from './ui/WorldInfoPanel'
import ActionLog from './ui/ActionLog'

function App() {
  const initialized = useRef(false)

  useEffect(() => {
    if (initialized.current) return
    initialized.current = true

    Promise.all([fetchWorld(), fetchPlayer(), fetchEvents()])
      .then(([worldData, player, events]) => {
        console.log('[World Data]', worldData)
        console.log('[Player Data]', player)

        const { setPlayer, setWorldState } = useGameStore.getState()
        setPlayer(player)
        setWorldState(worldData.worldState)

        initGame(worldData, player, events)
        startTickSystem()
      })
      .catch((err) => {
        console.error('[Init Error]', err)
      })
  }, [])

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ position: 'relative' }}>
        <div id="game-container" />
        <InteractionPanel />
      </div>
      <HUD />
      <WorldInfoPanel />
      <ActionLog />
    </div>
  )
}

export default App
