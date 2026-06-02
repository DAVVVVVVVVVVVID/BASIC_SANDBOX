import { useState } from 'react'
import { joinPlayer } from '../api/world'

interface Props {
  onJoined: (playerId: string, player: import('../types').Player) => void
}

export default function JoinScreen({ onJoined }: Props) {
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleJoin = async () => {
    const trimmed = name.trim()
    if (!trimmed) { setError('Please enter your name'); return }
    setLoading(true)
    setError('')
    try {
      const { playerId, player } = await joinPlayer(trimmed)
      onJoined(playerId, player)
    } catch (e) {
      setError('Failed to join, please check if the backend is running')
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
          Enter Game
        </div>
        <input
          type="text"
          placeholder="Enter your name"
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
          {loading ? 'Joining...' : 'Join'}
        </button>
      </div>
    </div>
  )
}
