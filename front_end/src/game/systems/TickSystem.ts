import { fetchWorld, fetchPlayer, fetchHistory } from '../../api/world'
import { useGameStore } from '../../store/gameStore'
import { EventBus } from '../EventBus'
import type { OtherPlayer } from '../../types'

export function startTickSystem(playerId: string): () => void {
  const id = window.setInterval(async () => {
    try {
      const [worldData, player, log] = await Promise.all([
        fetchWorld(),
        fetchPlayer(playerId),
        fetchHistory(),
      ])

      // player 返回 null 说明后端已重启/player 被清除，退回登录界面
      if (player === null) {
        window.clearInterval(id)
        useGameStore.getState().setMyPlayerId(null)
        return
      }

      const { setWorldState, setPlayer, setActionLog, setTiles, setOtherPlayers } = useGameStore.getState()
      setWorldState(worldData.worldState)
      setPlayer(player)
      setActionLog(log)
      setTiles(worldData.tiles)
      setOtherPlayers(worldData.players.filter((p: OtherPlayer) => p.id !== playerId))

      if (player.pendingMessage) {
        EventBus.emit('show-interaction', { message: player.pendingMessage })
      }
    } catch (err) {
      console.error('[Tick Error]', err)
    }
  }, 200)

  return () => window.clearInterval(id)
}
