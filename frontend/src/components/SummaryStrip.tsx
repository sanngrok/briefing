import type { ReactNode } from 'react'
import type { Signal, Severity } from '../api/client'
import type { Status } from './LoadState'

const RANK: Record<Severity, number> = { low: 1, mid: 2, high: 3 }
const LABEL: Record<Severity, string> = { low: '낮음', mid: '중간', high: '높음' }

// 지표마다 파스텔 아이콘 — 숫자만 늘어선 회색 칸보다 무엇을 세는지 한눈에 읽힌다.
const ICON: Record<string, ReactNode> = {
  bell: (
    <path d="M6 16.5V11a6 6 0 1 1 12 0v5.5l1.5 2h-15zM10 20.5a2 2 0 0 0 4 0" />
  ),
  gauge: (
    <>
      <path d="M4.5 17a8 8 0 1 1 15 0" />
      <path d="M12 13.5 15.5 9" />
    </>
  ),
  down: (
    <path d="M4 7l6 6 3.5-3.5L20 16M20 11v5h-5" />
  ),
  eye: (
    <>
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  paper: (
    <>
      <rect x="4" y="3.5" width="16" height="17" rx="2.5" />
      <path d="M8 8h8M8 12h8M8 16h5" />
    </>
  ),
}

function KpiIcon({ name, tone }: { name: keyof typeof ICON; tone: string }) {
  return (
    <span className={`kpi-icon tone-${tone}`} aria-hidden="true">
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {ICON[name]}
      </svg>
    </span>
  )
}

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

// 상단 요약 지표: 오늘 시그널 / 최고 심각도 / 급락 시그널 / 추적 종목 / 주요 뉴스
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
        <KpiIcon name="bell" tone="blue" />
        <div className="kpi-label">오늘 시그널</div>
        <KpiValue status={status.signals}>
          {total}
          <span className="kpi-unit">건</span>
        </KpiValue>
      </div>
      <div className="kpi-card">
        <KpiIcon name="gauge" tone="orange" />
        <div className="kpi-label">최고 심각도</div>
        <KpiValue status={status.signals} className={maxSev ? `sevtext-${maxSev}` : ''}>
          {maxSev ? LABEL[maxSev] : '—'}
        </KpiValue>
      </div>
      <div className="kpi-card">
        <KpiIcon name="down" tone="purple" />
        <div className="kpi-label">급락 시그널</div>
        <KpiValue status={status.signals} className={neg > 0 ? 'sevtext-high' : ''}>
          {neg}
          <span className="kpi-unit">건</span>
        </KpiValue>
      </div>
      <div className="kpi-card">
        <KpiIcon name="eye" tone="teal" />
        <div className="kpi-label">추적 종목</div>
        <KpiValue status={status.tickers}>
          {tickerCount}
          <span className="kpi-unit">개</span>
        </KpiValue>
      </div>
      <div className="kpi-card">
        <KpiIcon name="paper" tone="green" />
        <div className="kpi-label">주요 뉴스</div>
        <KpiValue status={status.news}>
          {newsCount}
          <span className="kpi-unit">건</span>
        </KpiValue>
      </div>
    </div>
  )
}
