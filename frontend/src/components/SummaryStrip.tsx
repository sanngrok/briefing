import type { ReactNode } from 'react'
import type { Signal, Severity } from '../api/client'
import type { Status } from './LoadState'

const RANK: Record<Severity, number> = { low: 1, mid: 2, high: 3 }
const LABEL: Record<Severity, string> = { low: '낮음', mid: '중간', high: '높음' }

/**
 * KPI 숫자는 도착하기 전에 0 을 보여 주면 안 된다 — "오늘 시그널 0" 은 아직 안 온
 * 것이 아니라 잠잠한 날이라는 뜻으로 읽힌다. 로딩 중에는 자리만 잡고, 실패한
 * 지표는 흐린 대시로 둔다.
 */
function KpiValue({
  status,
  className = '',
  children,
}: {
  status: Status
  className?: string
  children: ReactNode
}) {
  if (status === 'loading') {
    return (
      <div className="kpi-value">
        <span className="skel-inline" aria-hidden="true" />
      </div>
    )
  }
  if (status === 'error') {
    return (
      <div className="kpi-value kpi-fail" title="불러오지 못했습니다">
        —
      </div>
    )
  }
  return <div className={`kpi-value ${className}`}>{children}</div>
}

// 상단 요약 지표 스트립: 오늘 시그널 / 최고 심각도 / 급락 시그널 / 추적 종목
export function SummaryStrip({
  signals,
  tickerCount,
  newsCount,
  status,
}: {
  signals: Signal[]
  tickerCount: number
  newsCount: number
  status: { signals: Status; tickers: Status; news: Status }
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
        <KpiValue status={status.signals}>{total}</KpiValue>
      </div>
      <div className="kpi-card">
        <div className="kpi-label">최고 심각도</div>
        <KpiValue status={status.signals} className={maxSev ? `sevtext-${maxSev}` : ''}>
          {maxSev ? LABEL[maxSev] : '—'}
        </KpiValue>
      </div>
      <div className="kpi-card">
        <div className="kpi-label">급락 시그널</div>
        <KpiValue status={status.signals} className={neg > 0 ? 'sevtext-high' : ''}>
          {neg}
        </KpiValue>
      </div>
      <div className="kpi-card">
        <div className="kpi-label">추적 종목</div>
        <KpiValue status={status.tickers}>
          {tickerCount}
          <span className="kpi-unit">개</span>
        </KpiValue>
      </div>
      <div className="kpi-card">
        <div className="kpi-label">주요 뉴스</div>
        <KpiValue status={status.news}>
          {newsCount}
          <span className="kpi-unit">건</span>
        </KpiValue>
      </div>
    </div>
  )
}
