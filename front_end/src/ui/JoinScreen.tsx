import { useState } from 'react'
import { joinPlayer, joinAs, rejoinPlayer, fetchPlayersLite, setDnd } from '../api/world'
import { findResidentAchan, ACHAN } from '../game/identity'

interface Props {
  onJoined: (playerId: string, player: import('../types').Player, name: string, identity?: string) => void
}

export default function JoinScreen({ onJoined }: Props) {
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  /** 主播入口（world-v1.3 §12.12）：有常驻阿蝉就 rejoin 接管（不新建），没有就以 agent_id=achan 身份 join；接管后勿扰关 */
  const handleJoinAsAchan = async () => {
    setLoading(true); setError('')
    try {
      let playerId: string; let player: import('../types').Player
      const resident = findResidentAchan((await fetchPlayersLite().catch(() => ({ players: [] }))).players)
      if (resident) {
        const r = await rejoinPlayer(resident.id); playerId = r.playerId; player = r.player
      } else {
        const r = await joinAs(ACHAN.name, ACHAN.agent_id, false); playerId = r.playerId; player = r.player
      }
      try { const d = await setDnd(playerId, false); player = { ...player, dnd: d.dnd, tags: d.tags ?? player.tags } } catch { /* 旧后端没有 dnd 接口 */ }
      onJoined(playerId, player, ACHAN.name, ACHAN.agent_id)
    } catch {
      setError('以阿蝉身份登录失败，请检查后端（需 world-v1.3+）')
    } finally {
      setLoading(false)
    }
  }

  const handleJoin = async () => {
    const trimmed = name.trim()
    if (!trimmed) { setError('请输入名字'); return }
    setLoading(true)
    setError('')
    try {
      const { playerId, player } = await joinPlayer(trimmed)
      onJoined(playerId, player, trimmed)
    } catch {
      setError('加入失败，请检查后端是否启动')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: '#0d0d1a',
    }}>
      <div style={{
        background: '#1a1a2e', border: '1px solid #333', borderRadius: 12,
        padding: '40px 48px', display: 'flex', flexDirection: 'column',
        alignItems: 'center', gap: 16, minWidth: 320,
      }}>
        <div style={{ color: '#eee', fontSize: 22, fontWeight: 'bold', marginBottom: 8 }}>
          进入游戏
        </div>
        <input
          type="text"
          placeholder="输入你的名字"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleJoin()}
          maxLength={20}
          style={{
            width: '100%', padding: '10px 14px', borderRadius: 6, fontSize: 15,
            background: '#111', border: '1px solid #444', color: '#eee',
            outline: 'none', boxSizing: 'border-box',
          }}
          autoFocus
        />
        {error && <div style={{ color: '#f88', fontSize: 13 }}>{error}</div>}
        <button
          onClick={handleJoin}
          disabled={loading}
          style={{
            width: '100%', padding: '10px', borderRadius: 6, border: 'none',
            background: loading ? '#333' : '#4a90e2', color: '#fff',
            fontSize: 15, fontWeight: 'bold', cursor: loading ? 'default' : 'pointer',
          }}
        >
          {loading ? '加入中...' : '加入'}
        </button>
        <div style={{ width: '100%', borderTop: '1px solid #333', margin: '4px 0' }} />
        <button
          onClick={handleJoinAsAchan}
          disabled={loading}
          title="主播入口：接管常驻的阿蝉（agent_id=achan），钥匙 / QQ / 家按阿蝉算；登录后勿扰自动关，关页面自动开"
          style={{
            width: '100%', padding: '10px', borderRadius: 6, border: '1px solid #805ad5',
            background: loading ? '#333' : '#2d2550', color: '#e9d8fd',
            fontSize: 14, fontWeight: 'bold', cursor: loading ? 'default' : 'pointer',
          }}
        >
          🎙 以阿蝉身份登录（主播）
        </button>
      </div>
    </div>
  )
}
