import test from 'node:test'
import assert from 'node:assert/strict'
import { findResidentAchan } from '../src/game/identity'

test('findResidentAchan：优先 agent_id=achan，其次名叫阿蝉，否则 null', () => {
  const mk = (id: string, agent: string | null, name: string) => ({ id, agent_id: agent, profile: { name, id, age: 20 } }) as unknown as import('../src/types').Player
  assert.equal(findResidentAchan([mk('a', 'whale', '鲸仔'), mk('b', 'achan', '阿蝉')])?.id, 'b')
  assert.equal(findResidentAchan([mk('c', null, '阿蝉')])?.id, 'c')
  assert.equal(findResidentAchan([mk('a', 'whale', '鲸仔')]), null)
  assert.equal(findResidentAchan(undefined), null)
})
