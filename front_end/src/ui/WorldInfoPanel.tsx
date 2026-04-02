import { useGameStore } from '../store/gameStore'

const WEATHER_LABEL: Record<string, string> = {
  sunny:  '晴天 ☀',
  cloudy: '多云 ☁',
  rain:   '雨天 🌧',
}

export default function WorldInfoPanel() {
  const worldState = useGameStore((s) => s.worldState)
  if (!worldState) return null

  return (
    <div style={{
      position: 'absolute',
      top: 16,
      right: 16,
      background: 'rgba(15, 15, 30, 0.85)',
      border: '1px solid #4a5568',
      borderRadius: 8,
      padding: '10px 14px',
      color: '#e2e8f0',
      fontSize: 13,
      userSelect: 'none',
      textAlign: 'right',
      lineHeight: 1.8,
    }}>
      <div>{worldState.isDay ? '白天' : '夜晚'}</div>
      <div>{worldState.date} {worldState.time}</div>
      <div>{WEATHER_LABEL[worldState.weather] ?? worldState.weather}</div>
    </div>
  )
}
