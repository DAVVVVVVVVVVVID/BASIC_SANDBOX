import { fetchWorld, fetchPlayer } from '../../api/world'
import { useGameStore } from '../../store/gameStore'

export function startTickSystem(): () => void {
  const id = window.setInterval(async () => {
    try {
      const [worldData, player] = await Promise.all([fetchWorld(), fetchPlayer()])
      const { setWorldState, setPlayer } = useGameStore.getState()
      setWorldState(worldData.worldState)
      setPlayer(player)
    } catch (err) {
      console.error('[Tick Error]', err)
    }
  }, 200)

  return () => window.clearInterval(id)
}
