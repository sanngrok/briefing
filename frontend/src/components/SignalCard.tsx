import type { Signal, Severity } from '../api/client'
import { StockAvatar } from './StockAvatar'

const SEVERITY_LABEL: Record<Severity, string> = {
  high: '심각도 높음',
  mid: '심각도 중간',
  low: '심각도 낮음',
}

// 감정 방향은 뉴스 호재/악재와 같은 관행(호재 빨강 · 악재 파랑)으로 칠한다.
const TYPE: Record<string, { label: string; dir: 'good' | 'bad' }> = {
  sentiment_surge_pos: { label: '감정 급등', dir: 'good' },
  sentiment_surge_neg: { label: '감정 급락', dir: 'bad' },
}

export function SignalCard({ signal }: { signal: Signal }) {
  const delta =
    typeof signal.evidence?.delta === 'number' ? (signal.evidence.delta as number) : null
  const newsCount =
    typeof signal.evidence?.news_count === 'number'
      ? (signal.evidence.news_count as number)
      : null
  const name = signal.name ?? signal.symbol ?? '-'
  const type = TYPE[signal.type]

  return (
    <div className={`sigcard sev-${signal.severity}`}>
      <div className="sigcard-head">
        <StockAvatar name={name} />
        <div className="sigcard-title">
          <span className="sigcard-name">{name}</span>
          {signal.symbol && signal.symbol !== name && (
            <span className="sigcard-symbol mono">{signal.symbol}</span>
          )}
        </div>
        <span className="sigcard-badge">{SEVERITY_LABEL[signal.severity]}</span>
      </div>

      <div className="sigcard-body">
        <span className={`sigcard-type ${type ? `type-${type.dir}` : ''}`}>
          {type ? `${type.dir === 'good' ? '▲' : '▼'} ${type.label}` : signal.type}
        </span>
        {delta !== null && (
          <span className="sigcard-delta mono">
            감정 변화 {delta > 0 ? '+' : ''}
            {delta.toFixed(2)}
          </span>
        )}
      </div>

      <div className="sigcard-meta">
        {newsCount !== null ? `관련 기사 ${newsCount}건` : ''}
        {newsCount !== null ? ' · ' : ''}
        <span className="mono">{signal.date}</span>
      </div>
    </div>
  )
}
