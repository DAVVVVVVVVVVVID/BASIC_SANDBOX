import { fetchWorld, fetchPlayer, fetchHistory } from '../../api/world'
import { useGameStore } from '../../store/gameStore'
import { EventBus } from '../EventBus'

export function startTickSystem(): () => void {
  const id = window.setInterval(async () => {
    try {
      const [worldData, player, log] = await Promise.all([
        fetchWorld(),
        fetchPlayer(),
        fetchHistory(),
      ])
      const { setWorldState, setPlayer, setActionLog, setTiles } = useGameStore.getState()
      setWorldState(worldData.worldState)
      setPlayer(player)
      setActionLog(log)
      setTiles(worldData.tiles)

      if (player.pendingMessage) {
        EventBus.emit('show-interaction', { message: player.pendingMessage })
      }
    } catch (err) {
      console.error('[Tick Error]', err)
    }
  }, 200)

  return () => window.clearInterval(id)
}
