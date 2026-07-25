import type { Signal, Severity } from '../api/client'

// severity 색상 매핑
const SEVERITY_STYLE: Record<Severity, { label: string; color: string; bg: string }> = {
  high: { label: '높음', color: '#b91c1c', bg: '#fee2e2' },
  mid: { label: '중간', color: '#b45309', bg: '#fef3c7' },
  low: { label: '낮음', color: '#334155', bg: '#e2e8f0' },
}

const TYPE_LABEL: Record<string, string> = {
  sentiment_surge_pos: '감정 급등 (긍정)',
  sentiment_surge_neg: '감정 급락 (부정)',
}

export function SignalCard({ signal }: { signal: Signal }) {
  const s = SEVERITY_STYLE[signal.severity]
  const delta =
    typeof signal.evidence?.delta === 'number' ? (signal.evidence.delta as number) : null

  return (
    <div className="card" style={{ borderLeft: `4px solid ${s.color}` }}>
      <div className="card-head">
        <span className="ticker">{signal.name ?? signal.symbol ?? '-'}</span>
        <span className="badge" style={{ color: s.color, background: s.bg }}>
          {s.label}
        </span>
      </div>
      <div className="card-type">{TYPE_LABEL[signal.type] ?? signal.type}</div>
      <div className="card-meta">
        {signal.date}
        {delta !== null ? ` · Δ ${delta.toFixed(2)}` : ''}
      </div>
    </div>
  )
}
