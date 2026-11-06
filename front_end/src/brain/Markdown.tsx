import type { ReactNode } from 'react'

/** 极简 Markdown 渲染（够用于日程 / 计划 / 日摘要 / 记忆 .md）：标题、列表（含 - [x]）、表格、代码块折叠、段落。不解析 HTML。 */
export default function Markdown({ text }: { text: string }) {
  const lines = text.replace(/\r/g, '').split('\n')
  const out: ReactNode[] = []
  let i = 0, key = 0
  const inline = (s: string) => {
    const parts: ReactNode[] = []
    const re = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g
    let last = 0, m: RegExpExecArray | null
    while ((m = re.exec(s))) {
      if (m.index > last) parts.push(s.slice(last, m.index))
      const tok = m[0]
      if (tok.startsWith('**')) parts.push(<strong key={key++}>{tok.slice(2, -2)}</strong>)
      else if (tok.startsWith('`')) parts.push(<code key={key++} style={{ background: '#2c2c2a', padding: '0 4px', borderRadius: 3 }}>{tok.slice(1, -1)}</code>)
      else { const mm = /\[([^\]]+)\]\(([^)]+)\)/.exec(tok)!; parts.push(<span key={key++} style={{ color: '#86b6ef' }} title={mm[2]}>{mm[1]}</span>) }
      last = m.index + tok.length
    }
    if (last < s.length) parts.push(s.slice(last))
    return parts
  }
  while (i < lines.length) {
    const l = lines[i]
    if (/^```/.test(l)) {
      const buf: string[] = []; i++
      while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++])
      i++
      out.push(<details key={key++} style={{ margin: '6px 0' }}><summary style={{ color: '#8a897f', cursor: 'pointer', fontSize: 12 }}>原始数据（{buf.length} 行）</summary><pre style={{ fontSize: 11, color: '#c3c2b7', whiteSpace: 'pre-wrap', maxHeight: 240, overflow: 'auto', background: '#161615', padding: 8, borderRadius: 6 }}>{buf.join('\n')}</pre></details>)
      continue
    }
    const h = /^(#{1,6})\s+(.*)$/.exec(l)
    if (h) { const lvl = h[1].length; out.push(<div key={key++} style={{ fontWeight: 700, fontSize: lvl === 1 ? 18 : lvl === 2 ? 15 : 14, color: '#f0efec', margin: '10px 0 4px' }}>{inline(h[2])}</div>); i++; continue }
    if (/^\|/.test(l)) {
      const rows: string[][] = []
      while (i < lines.length && /^\|/.test(lines[i])) {
        const cells = lines[i].trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim())
        if (!cells.every(c => /^:?-{2,}:?$/.test(c))) rows.push(cells)
        i++
      }
      out.push(<table key={key++} style={{ borderCollapse: 'collapse', fontSize: 12, margin: '6px 0', width: '100%' }}><tbody>
        {rows.map((r, ri) => <tr key={ri} style={{ borderBottom: '1px solid #2c2c2a' }}>{r.map((c, ci) => ri === 0
          ? <th key={ci} style={{ textAlign: 'left', padding: '4px 6px', color: '#c3c2b7', fontWeight: 600 }}>{inline(c)}</th>
          : <td key={ci} style={{ padding: '4px 6px', color: '#e2e2dc', verticalAlign: 'top' }}>{inline(c)}</td>)}</tr>)}
      </tbody></table>)
      continue
    }
    const li = /^\s*[-*]\s+(.*)$/.exec(l)
    if (li) {
      const items: string[] = []
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*[-*]\s+/, '')); i++ }
      out.push(<ul key={key++} style={{ margin: '4px 0 4px 18px', padding: 0 }}>{items.map((it, k) => {
        const done = /^\[x\]\s*/i.test(it), todo = /^\[ \]\s*/.test(it)
        const body = it.replace(/^\[[ x]\]\s*/i, '')
        return <li key={k} style={{ margin: '2px 0', color: done ? '#8a897f' : '#e2e2dc', listStyle: done || todo ? 'none' : 'disc' }}>{done ? '☑ ' : todo ? '☐ ' : ''}{inline(body)}</li>
      })}</ul>)
      continue
    }
    if (!l.trim()) { i++; continue }
    const para: string[] = [l]; i++
    while (i < lines.length && lines[i].trim() && !/^(#|\||\s*[-*]\s|```)/.test(lines[i])) para.push(lines[i++])
    out.push(<p key={key++} style={{ margin: '4px 0', lineHeight: 1.6, color: '#e2e2dc' }}>{inline(para.join(' '))}</p>)
  }
  return <div style={{ fontSize: 13 }}>{out}</div>
}
