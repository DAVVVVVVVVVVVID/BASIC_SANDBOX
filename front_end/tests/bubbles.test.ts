// 单测：同一人头顶短时间内两条气泡合并（W9 遗留：give 与 commission deliver 互相覆盖）
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { useGameStore } from '../src/store/gameStore'

test('2 s 内两条合成两行；久的替换', () => {
  const st = useGameStore.getState()
  st.pushBubble('p1', '🎁 把歌送给了餐厅老板', 5000)
  st.pushBubble('p1', '✅ 交付了《冒烟委托》 +188 金币', 6000)
  let b = useGameStore.getState().bubbles.find(x => x.entityId === 'p1')!
  assert.equal(b.content, '🎁 把歌送给了餐厅老板\n✅ 交付了《冒烟委托》 +188 金币')
  // 把它弄旧（剩余 < ttl-2s）再推一条 → 直接替换
  useGameStore.setState({ bubbles: [{ ...b, until: performance.now() + 1000 }] })
  st.pushBubble('p1', '🍞 吃了面包', 5000)
  b = useGameStore.getState().bubbles.find(x => x.entityId === 'p1')!
  assert.equal(b.content, '🍞 吃了面包')
  // 重复内容不叠加
  st.pushBubble('p1', '🍞 吃了面包', 5000)
  assert.equal(useGameStore.getState().bubbles.find(x => x.entityId === 'p1')!.content, '🍞 吃了面包')
})
