import { Component, type ErrorInfo, type ReactNode } from 'react'

/**
 * 面板级 ErrorBoundary（总控 11-18：跟随时点「聊天」一个 TypeError 卸掉整棵 React 树 → 连游戏画布一起黑屏）。
 * 包在每个面板 / 抽屉 / QQ / 聊天外面：某块出错只显示「这个面板出错了」+ 重试，其余照常。
 * resetKey 变了（换面板 / 换跟随对象）自动复位。variant=overlay 用于整个外壳：只浮一条提示，不挡画布。
 */
interface Props { name: string; resetKey?: unknown; variant?: 'panel' | 'overlay'; children: ReactNode }
interface State { err: Error | null; key: unknown }

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { err: null, key: this.props.resetKey }
  static getDerivedStateFromError(err: Error): Partial<State> { return { err } }
  static getDerivedStateFromProps(p: Props, s: State): Partial<State> | null {
    return p.resetKey !== s.key ? { err: null, key: p.resetKey } : null
  }
  componentDidCatch(err: Error, info: ErrorInfo) {
    console.error(`[ErrorBoundary:${this.props.name}]`, err, info.componentStack)
  }
  render() {
    const { err } = this.state
    if (!err) return this.props.children
    if (this.props.variant === 'overlay') {
      return (
        <div data-testid={`error-boundary-${this.props.name}`} style={{ position: 'fixed', left: '50%', top: 12, transform: 'translateX(-50%)', zIndex: 1000, background: '#FFF8EC', color: '#3B2F2F', border: '2px solid #FF8A73', borderRadius: 8, padding: '8px 14px', fontSize: 14, display: 'flex', gap: 10, alignItems: 'center', pointerEvents: 'auto' }}>
          <span>界面出错了（{this.props.name}）</span>
          <button className="k" onClick={() => this.setState({ err: null })}>重试</button>
          <button className="k" onClick={() => window.location.reload()}>重新载入</button>
        </div>
      )
    }
    return (
      <div data-testid={`error-boundary-${this.props.name}`} style={{ padding: 16, textAlign: 'center', color: '#7A6A5A', fontSize: 14, pointerEvents: 'auto' }}>
        <div style={{ marginBottom: 6 }}>这个面板出错了</div>
        <div style={{ fontSize: 11, color: '#A89A88', marginBottom: 8, wordBreak: 'break-all' }}>{String(err.message ?? err).slice(0, 120)}</div>
        <button className="k" onClick={() => this.setState({ err: null })}>重试</button>
      </div>
    )
  }
}
