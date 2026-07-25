import type { Signal, Severity } from '../api/client'

const SEVERITY_LABEL: Record<Severity, string> = {
  high: '높음',
  mid: '중간',
  low: '낮음',
}

const TYPE_LABEL: Record<string, string> = {
  sentiment_surge_pos: '감정 급등 (긍정)',
  sentiment_surge_neg: '감정 급락 (부정)',
}

export function SignalCard({ signal }: { signal: Signal }) {
  const delta =
    typeof signal.evidence?.delta === 'number' ? (signal.evidence.delta as number) : null
  const newsCount =
    typeof signal.evidence?.news_count === 'number'
      ? (signal.evidence.news_count as number)
      : null

  return (
    <div className={`sigcard sev-${signal.severity}`}>
      <div className="sigcard-head">
        <span className="sigcard-name">{signal.name ?? signal.symbol ?? '-'}</span>
        <span className="sigcard-badge">{SEVERITY_LABEL[signal.severity]}</span>
      </div>
      <div className="sigcard-type">{TYPE_LABEL[signal.type] ?? signal.type}</div>
      <div className="sigcard-meta">
        {signal.date}
        {delta !== null ? ` · Δ ${delta.toFixed(2)}` : ''}
        {newsCount !== null ? ` · 기사 ${newsCount}건` : ''}
      </div>
    </div>
  )
}
