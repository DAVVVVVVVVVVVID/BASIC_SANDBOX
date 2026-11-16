import type { ReactNode } from 'react'
import { C, panel } from './theme'

/** 从底栏上方弹出的面板（mockC2）：居中偏下、不盖四角；title 条 + ✕；dark = 内容区用暗色（嵌旧面板时可读） */
export default function PanelFrame({ title, onClose, width = 560, dark = false, children }: { title: string; onClose: () => void; width?: number; dark?: boolean; children: ReactNode }) {
  return (
    <div className="popup" data-testid="rpg-popup" onKeyDown={e => { if (e.key === 'Escape') onClose() }}
      style={panel({ position: 'absolute', left: '50%', bottom: 100, transform: 'translateX(-50%)', width, maxWidth: 'calc(100vw - 480px)', maxHeight: 'calc(100vh - 200px)', display: 'flex', flexDirection: 'column', pointerEvents: 'auto', padding: 0, overflow: 'hidden' })}>
      <div style={{ display: 'flex', alignItems: 'center', padding: '8px 14px', borderBottom: `2px solid ${C.sky}`, background: 'rgba(255,255,255,0.5)' }}>
        <b style={{ fontSize: 17, flex: 1, textAlign: 'center' }}>{title}</b>
        <button className="rb" onClick={onClose} title="关闭（Esc）" data-testid="rpg-close" style={{ background: 'transparent', border: 'none', color: C.coral, fontSize: 20, lineHeight: 1, cursor: 'pointer', padding: '0 2px' }}>✕</button>
      </div>
      <div className={dark ? '' : 'embed'} style={{ overflowY: 'auto', padding: 10, background: dark ? '#1f2135' : 'transparent', color: dark ? '#e2e8f0' : C.ink, flex: 1, minHeight: 0 }}>
        {children}
      </div>
    </div>
  )
}
