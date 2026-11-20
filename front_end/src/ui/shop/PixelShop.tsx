import type { CSSProperties, ReactNode } from 'react'
import { KIND_SKIN, SHOP_ASSET, rowsOf, type PixelCard, type ShopKind } from './shopSkin'

/**
 * 像素商店（主播 11-20 认可 v2：店招 → 柜体九宫格里 3 列等大卡片 → 底部一条 → 右下店主头像；三家只换材质）。
 * 直播导播页与操控页共用：scale 控整体大小（导播 ≈ 1，手机 ≈ 0.62）；onPick 给了才可点（操控页选货），导播页只读。
 * selectedKey 套金框，stampKey 盖「成交」章（短暂），soldOut 在图标上斜贴售罄条、价签显示「售罄」。
 */
const FONT = '"Fusion Pixel 12px", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif'
const INK = '#3B2F2F'

export default function PixelShop({ kind, title, cards, selectedKey, stampKey, onPick, footer, gold, scale = 1, ownerKey, emptyText }: {
  kind: ShopKind; title: string; cards: PixelCard[]; selectedKey?: string | null; stampKey?: string | null; onPick?: (c: PixelCard) => void
  footer?: ReactNode; gold?: number | null; scale?: number; ownerKey?: string; emptyText?: string
}) {
  const skin = KIND_SKIN[kind]
  const u = (n: number) => Math.round(n * scale)
  const nine = (img: string, slice: number, width: number): CSSProperties => ({
    borderStyle: 'solid', borderWidth: width, borderColor: 'transparent',
    borderImage: `url(${SHOP_ASSET(img)}) ${slice} fill / ${width}px stretch`, imageRendering: 'pixelated',
  })
  const rows = rowsOf(cards)
  return (
    <div data-testid={`pixel-shop-${kind}`} style={{ position: 'relative', fontFamily: FONT, color: INK, userSelect: 'none', paddingBottom: u(8) }}>
      {/* 店招：空牌 + 页面写字 */}
      <div style={{ position: 'relative', margin: '0 auto', width: '100%', aspectRatio: `480 / ${skin.bannerH}`, backgroundImage: `url(${SHOP_ASSET(skin.banner)})`, backgroundSize: '100% 100%', imageRendering: 'pixelated', zIndex: 1 }}>
        <div style={{ position: 'absolute', left: 0, right: 0, top: kind === 'restaurant' ? '38%' : kind === 'grocery' ? '16%' : '14%', height: '40%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: u(30), fontWeight: 700, letterSpacing: u(2), textShadow: '0 1px 0 rgba(255,255,255,0.5)' }}>{title}</div>
      </div>
      {/* 柜体 + 卡片网格 */}
      <div style={{ ...nine(skin.frame, 48, u(30)), marginTop: u(-14), padding: u(6), minHeight: u(160) }}>
        {cards.length === 0 && <div style={{ padding: u(24), textAlign: 'center', fontSize: u(18), color: kind === 'restaurant' ? '#F3EAD8' : INK }}>{emptyText ?? '暂时没货'}</div>}
        {rows.map((row, ri) => (
          <div key={ri} style={{ position: 'relative', marginBottom: u(10) }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: u(10) }}>
              {row.map(c => <Card key={c.key} c={c} card={skin.card} u={u} nine={nine} selected={c.key === selectedKey} stamped={c.key === stampKey} onPick={onPick} />)}
            </div>
            {kind === 'grocery' && <div style={{ height: u(14), marginTop: u(6), backgroundImage: `url(${SHOP_ASSET('shelf_plank')})`, backgroundSize: `${u(96)}px 100%`, backgroundRepeat: 'repeat-x', imageRendering: 'pixelated' }} />}
          </div>
        ))}
        {/* 底部一条 + 金币 + 店主头像 */}
        <div style={{ display: 'flex', alignItems: 'stretch', gap: u(10), marginTop: u(6), minHeight: u(76), paddingRight: u(96) }}>
          <div style={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', ...(kind !== 'restaurant' ? { ...nine('stock_box', 14, u(10)), padding: `0 ${u(4)}px` } : {}) }}>{footer}</div>
          {gold !== undefined && (
            <div style={{ ...nine('stock_box', 14, u(10)), display: 'flex', alignItems: 'center', gap: u(6), padding: `0 ${u(6)}px`, minWidth: u(88), fontSize: u(22), fontWeight: 700 }}>
              <img src={SHOP_ASSET('coin')} alt="" width={u(26)} height={u(26)} style={{ imageRendering: 'pixelated' }} />{gold === null ? '—' : gold}
            </div>
          )}
        </div>
      </div>
      <img src={`assets/ui/avatars/${ownerKey ?? skin.ownerKey}_112.png`} alt="" width={u(104)} height={u(104)} style={{ position: 'absolute', right: u(-6), bottom: u(0), imageRendering: 'pixelated', borderRadius: u(14), border: `${u(3)}px solid #F2B84B`, background: '#FFF8EC', boxShadow: '2px 2px 0 rgba(0,0,0,0.25)', zIndex: 2 }} />
    </div>
  )
}

function Card({ c, card, u, nine, selected, stamped, onPick }: { c: PixelCard; card: string; u: (n: number) => number; nine: (img: string, slice: number, width: number) => CSSProperties; selected: boolean; stamped: boolean; onPick?: (c: PixelCard) => void }) {
  return (
    <div data-testid={`pixel-card-${c.key}`} onClick={onPick ? () => onPick(c) : undefined} title={c.note ?? c.name}
      style={{ position: 'relative', ...nine(card, 28, u(16)), padding: u(2), cursor: onPick ? 'pointer' : 'default', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: u(4), opacity: c.soldOut ? 0.92 : 1 }}>
      <div style={{ height: u(72), display: 'flex', alignItems: 'center', justifyContent: 'center', filter: c.soldOut ? 'grayscale(0.7)' : undefined, position: 'relative' }}>
        {c.icon ? <img src={c.icon} alt="" width={u(68)} height={u(68)} style={{ imageRendering: 'pixelated' }} /> : <span style={{ fontSize: u(46) }}>{c.emoji ?? '📦'}</span>}
        {c.tier === 'rare' && <span style={{ position: 'absolute', right: u(-6), top: u(-4), fontSize: u(16) }}>✨</span>}
        {c.tier === 'legend' && <span style={{ position: 'absolute', right: u(-6), top: u(-4), fontSize: u(16) }}>🌟</span>}
        {/* 售罄贴条只斜贴在图标上，不盖名字和价签（总控 11-20） */}
        {c.soldOut && <img data-testid="pixel-soldout" src={SHOP_ASSET('sold_out_strip')} alt="售罄" style={{ position: 'absolute', left: '50%', top: '50%', width: u(104), transform: 'translate(-50%, -50%) rotate(-14deg)', imageRendering: 'pixelated', pointerEvents: 'none' }} />}
      </div>
      <div style={{ fontSize: u(18), fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '100%' }}>{c.name}</div>
      <div style={{ display: 'flex', gap: u(4), width: '100%', alignItems: 'stretch' }}>
        <div style={{ ...nine('stock_box', 14, u(8)), flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: u(3), fontSize: u(17), fontWeight: 700, padding: `${u(1)}px 0`, minWidth: 0 }}>
          {!c.soldOut && c.price !== null && <img src={SHOP_ASSET('coin')} alt="" width={u(16)} height={u(16)} style={{ imageRendering: 'pixelated' }} />}
          <span style={{ whiteSpace: 'nowrap', color: c.soldOut ? '#B23B2E' : undefined }}>{c.soldOut ? '售罄' : c.priceText ?? (c.price ?? '—')}</span>
        </div>
        {c.sub !== null && <div style={{ ...nine('stock_box', 14, u(8)), display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: u(13), fontWeight: 700, minWidth: u(34), padding: `0 ${u(1)}px`, whiteSpace: 'nowrap' }}>{c.soldOut && /^\d+$/.test(c.sub) ? '0' : c.sub}</div>}
      </div>
      {selected && <div style={{ position: 'absolute', inset: u(-6), ...nine('select_frame', 24, u(10)), pointerEvents: 'none', animation: 'psGlow 1.2s ease-in-out infinite alternate' }} />}
      {stamped && <img src={SHOP_ASSET('stamp_deal')} alt="成交" style={{ position: 'absolute', left: '18%', top: '10%', width: '64%', imageRendering: 'pixelated', pointerEvents: 'none', animation: 'psStamp 420ms ease-out' }} />}
      <style>{`@keyframes psGlow { from { opacity: 0.65 } to { opacity: 1 } } @keyframes psStamp { from { transform: scale(1.8) rotate(-20deg); opacity: 0 } to { transform: none; opacity: 1 } }`}</style>
    </div>
  )
}
