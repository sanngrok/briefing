import type { Signal, Severity } from '../api/client'

const RANK: Record<Severity, number> = { low: 1, mid: 2, high: 3 }
const LABEL: Record<Severity, string> = { low: '낮음', mid: '중간', high: '높음' }

// 상단 요약 지표 스트립: 오늘 시그널 / 최고 심각도 / 급락 시그널 / 추적 종목
export function SummaryStrip({
  signals,
  tickerCount,
  newsCount,
}: {
  signals: Signal[]
  tickerCount: number
  newsCount: number
}) {
  const total = signals.length
  const neg = signals.filter((s) => s.type.includes('neg')).length

  let maxSev: Severity | null = null
  for (const s of signals) {
    if (!maxSev || RANK[s.severity] > RANK[maxSev]) maxSev = s.severity
  }

  return (
    <div className="kpi">
      <div className="kpi-card">
        <div className="kpi-label">오늘 시그널</div>
        <div className="kpi-value">{total}</div>
      </div>
      <div className="kpi-card">
        <div className="kpi-label">최고 심각도</div>
        <div className={`kpi-value ${maxSev ? `sevtext-${maxSev}` : ''}`}>
          {maxSev ? LABEL[maxSev] : '—'}
        </div>
      </div>
      <div className="kpi-card">
        <div className="kpi-label">급락 시그널</div>
        <div className={`kpi-value ${neg > 0 ? 'sevtext-high' : ''}`}>{neg}</div>
      </div>
      <div className="kpi-card">
        <div className="kpi-label">추적 종목</div>
        <div className="kpi-value">
          {tickerCount}
          <span className="kpi-unit">개</span>
        </div>
      </div>
      <div className="kpi-card">
        <div className="kpi-label">주요 뉴스</div>
        <div className="kpi-value">
          {newsCount}
          <span className="kpi-unit">건</span>
        </div>
      </div>
    </div>
  )
}
