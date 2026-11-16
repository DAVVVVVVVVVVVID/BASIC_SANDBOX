import { useState } from 'react'
import './rpg.css'
import { joinPlayer, joinAs, rejoinPlayer, fetchPlayersLite } from '../../api/world'
import { findResidentAchan, ACHAN } from '../../game/identity'
import { C, avatarUrl, kit } from './theme'

interface Props { onJoined: (playerId: string, player: import('../../types').Player, name: string, identity?: string) => void }

/**
 * 像素标题画面（主播 11-16 定稿 ④）：底图用 Godot 同款小镇截图（report 的 ref），缎带标题 + 大按钮「以阿蝉身份登录」+ 小框「其他名字加入」。
 * 登录逻辑与旧 JoinScreen 一致：有常驻阿蝉就 rejoin 接管，没有就 joinAs(achan)；不自动关勿扰（总控 11-14 选 A）。
 */
export default function JoinScreenRpg({ onJoined }: Props) {
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [more, setMore] = useState(false)

  const handleJoinAsAchan = async () => {
    setLoading(true); setError('')
    try {
      let playerId: string; let player: import('../../types').Player
      const resident = findResidentAchan((await fetchPlayersLite().catch(() => ({ players: [] }))).players)
      if (resident) { const r = await rejoinPlayer(resident.id); playerId = r.playerId; player = r.player }
      else { const r = await joinAs(ACHAN.name, ACHAN.agent_id, false); playerId = r.playerId; player = r.player }
      onJoined(playerId, player, ACHAN.name, ACHAN.agent_id)
    } catch { setError('以阿蝉身份登录失败，请检查后端（需 world-v1.3+）') } finally { setLoading(false) }
  }
  const handleJoin = async () => {
    const trimmed = name.trim()
    if (!trimmed) { setError('请输入名字'); return }
    setLoading(true); setError('')
    try { const { playerId, player } = await joinPlayer(trimmed); onJoined(playerId, player, trimmed) }
    catch { setError('加入失败，请检查后端是否启动') } finally { setLoading(false) }
  }

  return (
    <div className="rpg" style={{ position: 'fixed', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'linear-gradient(180deg, #BFE3F7 0%, #D8EFD4 60%, #B9DBA6 100%)', imageRendering: 'pixelated' }}>
      {/* 底纹：小镇全景截图淡淡铺底 */}
      <img src="assets/ui/login_bg.jpg" alt="" onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: 0.55, imageRendering: 'pixelated' }} />
      <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18, width: 'min(520px, 94vw)' }}>
        <div style={{ position: 'relative', width: 'min(520px, 94vw)', height: 86, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundImage: `url(${kit('login_ribbon')})`, backgroundSize: '100% 100%', imageRendering: 'pixelated' }}>
          <span style={{ fontSize: 'clamp(20px, 5.5vw, 30px)', fontWeight: 700, color: C.ink, letterSpacing: 2, marginTop: -6 }}>鲸仔小镇 · 操控台</span>
        </div>
        <div className="panel9" style={{ width: 'min(400px, 90vw)', padding: '14px 18px 18px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14, color: C.ink }}>
          <img className="px" src={avatarUrl('achan', 112)} width={96} height={96} alt="" style={{ borderRadius: 14, border: `3px solid ${C.sky}`, background: '#fff' }} />
          <div style={{ fontSize: 16, color: C.inkSoft }}>以阿蝉的身份进入小镇</div>
          <button onClick={handleJoinAsAchan} disabled={loading} data-testid="login-achan"
            style={{ width: 'min(300px, 76vw)', height: 64, border: 'none', background: `url(${kit('login_big_btn')}) center / 100% 100% no-repeat`, color: '#fff', fontSize: 22, fontWeight: 700, cursor: loading ? 'default' : 'pointer', imageRendering: 'pixelated', textShadow: '0 1px 0 rgba(0,0,0,0.25)' }}>
            {loading ? '进入中…' : '🎙 以阿蝉身份登录'}
          </button>
          {error && <div style={{ color: C.coral, fontSize: 13 }}>{error}</div>}
          <button className="k" onClick={() => setMore(m => !m)} style={{ fontSize: 13 }}>{more ? '收起' : '用别的名字加入…'}</button>
          {more && (
            <div style={{ display: 'flex', gap: 8, width: '100%' }}>
              <input type="text" placeholder="输入你的名字" value={name} onChange={e => setName(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleJoin()} maxLength={20} autoFocus
                style={{ flex: 1, padding: '8px 12px', border: `2px solid ${C.sky}`, borderRadius: 6, fontSize: 15, background: '#fff', color: C.ink, outline: 'none' }} />
              <button className="k teal" onClick={handleJoin} disabled={loading} style={{ minWidth: 72 }}>{loading ? '…' : '加入'}</button>
            </div>
          )}
        </div>
        <div style={{ fontSize: 12, color: C.inkSoft }}>快捷键 1–6 打开面板 · Esc 关闭 · 旧界面加 ?ui=old</div>
      </div>
    </div>
  )
}
