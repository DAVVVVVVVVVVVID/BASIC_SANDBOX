import type { MetaChip } from '../../game/shop'
import { metaChips } from '../../game/shop'

/** 物品 meta 小标签（品种 / 重量 / 品级 / 新鲜度；钓鱼系统 11-19）：商店面板、背包、跟随看背包共用；没有 meta 就什么都不画 */
const TONE: Record<string, { bg: string; fg: string }> = {
  common: { bg: '#EDE3D2', fg: '#7A6A5A' }, rare: { bg: '#DDEBFF', fg: '#2F5E8A' }, legendary: { bg: '#FFE7B3', fg: '#8A5A00' },
  fresh: { bg: '#DDF3EE', fg: '#1F7A6F' }, stale: { bg: '#FBEBC9', fg: '#8A6116' }, spoiled: { bg: '#FBDAD6', fg: '#B23B2E' },
}
export function Chip({ c }: { c: MetaChip }) {
  const t = TONE[c.tone ?? ''] ?? { bg: '#F1EBE0', fg: '#7A6A5A' }
  return <span title={c.label} style={{ fontSize: 11, padding: '1px 6px', borderRadius: 8, background: t.bg, color: t.fg, whiteSpace: 'nowrap', lineHeight: 1.5 }}>{c.value}</span>
}
export default function MetaChips({ meta, chips }: { meta?: Record<string, unknown> | null; chips?: MetaChip[] }) {
  const cs = chips ?? metaChips(meta)
  if (!cs.length) return null
  return <span data-testid="meta-chips" style={{ display: 'inline-flex', gap: 4, flexWrap: 'wrap', verticalAlign: 'middle' }}>{cs.map((c, i) => <Chip key={i} c={c} />)}</span>
}
