import type { QQContact, QQMessage } from '../api/qq'
/** QQ 本地状态的三个纯 reducer（全局 store 与「跟随看他的 QQ」的隔离面板共用） */
export interface QQState { contacts: QQContact[]; messages: QQMessage[]; available: boolean | null }
export const qqSetContacts = (s: QQState, c: QQContact[] | null): QQState => ({ ...s, contacts: c ?? s.contacts, available: c !== null })
export function qqMerge(s: QQState, m: QQMessage[]): QQState {
  if (!m.length) return s
  const byId = new Map(s.messages.map(x => [x.id, x]))
  for (const x of m) byId.set(x.id, { ...byId.get(x.id), ...x })
  return { ...s, messages: [...byId.values()].sort((a, b) => a.ts.localeCompare(b.ts)).slice(-500), available: true }
}
export function qqReplaceThread(s: QQState, belongs: (m: QQMessage) => boolean, m: QQMessage[]): QQState {
  const byId = new Map(s.messages.filter(x => !belongs(x)).map(x => [x.id, x]))
  for (const x of m) byId.set(x.id, x)
  return { ...s, messages: [...byId.values()].sort((a, b) => a.ts.localeCompare(b.ts)).slice(-1000), available: true }
}
