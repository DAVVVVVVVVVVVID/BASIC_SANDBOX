/**
 * 角色外观键与「名字 → 外观」规则（不依赖 Phaser，便于单测 `tests/charKey.test.ts`）。
 * 世界设定集 `docs/world-bible/04-npcs.md` 的六个角色全部显式匹配：
 * 鲸仔 → whale、阿蝉 → achan、小千（千小满）→ regular、餐厅老板（厨师）→ cook、杂货店老板（娘）→ grocer、老渔夫 → fisher。
 * 总控 11-07 晚：餐厅老板之前没命中任何规则、哈希落到含 regular 的池子，被画成了小千 → 加显式规则，并把 regular 从池子里拿掉（小千专属）。
 */
export const CHAR_KEYS = ['whale', 'achan', 'cook', 'grocer', 'fisher', 'regular', 'villager', 'whale_v1', 'achan_v1'] as const
export type CharKey = typeof CHAR_KEYS[number]

/** 未知名字的兜底池：只放「路人」类外观；regular 是小千专属、villager 已下线（主播 11-07 评分） */
export const NPC_POOL: readonly CharKey[] = ['cook', 'grocer', 'fisher']

/** 按名字 / 身份挑角色外观：六个设定角色显式匹配，否则按名字哈希稳定分配到 NPC_POOL */
export function charKeyFor(name: string, controller?: string): CharKey {
  const n = (name || '').toLowerCase()
  if (/鲸|whale/.test(n)) return 'whale'
  if (/阿蝉|achan|蝉/.test(n)) return 'achan'
  if (/小千|千小满|小满|xiaoqian|常客|regular/.test(n)) return 'regular'   // W8：regular 这套外观画成千小满（小千）
  if (/杂货|grocer|店老板娘/.test(n)) return 'grocer'
  if (/餐厅|餐馆|厨|cook|chef/.test(n)) return 'cook'
  if (/渔|fish/.test(n)) return 'fisher'
  if (/店/.test(n)) return 'grocer'   // 其余带「店」的（店主 / 店员）当杂货店的人
  if (controller === 'human') return 'achan'   // 作者进来操控默认是阿蝉
  let h = 0
  for (const ch of n) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return NPC_POOL[h % NPC_POOL.length]
}
