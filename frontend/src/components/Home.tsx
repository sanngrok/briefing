import type { ReactNode } from 'react'
import type { Mover, Movers, NewsItem, Signal, Severity } from '../api/client'
import type { Status } from './LoadState'
import { StockAvatar } from './StockAvatar'
import { hashOf } from '../lib/route'
import { formatKoDate } from '../lib/date'
import { countTones, newsTone } from '../lib/news'
import { direction, formatPct, formatSigned, formatWon } from '../lib/portfolio'
import type { PortfolioTotals } from '../lib/portfolio'
import type { AlertRow } from '../lib/alerts'

/*
 * 오늘 요약 = 토스 홈처럼 '입구 카드'를 세로로 쌓는다.
 *   - 한 카드 = 아이콘 · 큰 숫자(먼저) · 설명 한 줄(아래) · 오른쪽 알약/화살표
 *   - 누르면 그 메뉴로 간다. 자세한 건 각 메뉴에서 본다.
 * 돈(내 자산)이 맨 위, 그다음 오늘 바뀐 것(시그널·뉴스·급등락), 마지막에 리포트.
 */

const SEV_LABEL: Record<Severity, string> = { high: '높음', mid: '중간', low: '낮음' }
const SEV_RANK: Record<Severity, number> = { low: 1, mid: 2, high: 3 }
const MOVER_ROWS = 5

const ICON: Record<string, ReactNode> = {
  wallet: (
    <>
      <rect x="3" y="6" width="18" height="14" rx="3" />
      <path d="M16 13h2M3 10h18M7 6V4.5h10V6" />
    </>
  ),
  bell: <path d="M6 16.5V11a6 6 0 1 1 12 0v5.5l1.5 2h-15zM10 20.5a2 2 0 0 0 4 0" />,
  paper: (
    <>
      <rect x="4" y="3.5" width="16" height="17" rx="2.5" />
      <path d="M8 8h8M8 12h8M8 16h5" />
    </>
  ),
  chart: <path d="M4 4v16h16M7.5 15l3.5-4 3 2.5L19 8" />,
  report: (
    <>
      <path d="M14 3.5H7.5A2.5 2.5 0 0 0 5 6v12a2.5 2.5 0 0 0 2.5 2.5h9A2.5 2.5 0 0 0 19 18V8.5z" />
      <path d="M14 3.5v5h5M9 13h6M9 16.5h4" />
    </>
  ),
}

function Icon({ name, tone }: { name: keyof typeof ICON; tone: string }) {
  return (
    <span className={`hicon tone-${tone}`} aria-hidden="true">
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

function Chevron() {
  return (
    <svg className="hchev" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M9 5.5 15.5 12 9 18.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** 한 줄: 아이콘 · (큰 값 / 설명) · 오른쪽 */
function Row({
  icon,
  value,
  sub,
  right,
}: {
  icon: ReactNode
  value: ReactNode
  sub: ReactNode
  right?: ReactNode
}) {
  return (
    <div className="hrow">
      {icon}
      <div className="hrow-main">
        <span className="hrow-value">{value}</span>
        <span className="hrow-sub">{sub}</span>
      </div>
      {right}
    </div>
  )
}

/** 값 자리 — 로딩이면 회색 막대, 실패면 대시. 0 을 먼저 보여 주지 않는다. */
function Value({ status, children }: { status: Status; children: ReactNode }) {
  if (status === 'loading') return <span className="skel-inline" aria-label="불러오는 중" />
  if (status === 'error') return <span className="hrow-fail">불러오지 못했어요</span>
  return <>{children}</>
}

function LinkCard({ to, label, children }: { to: string; label: string; children: ReactNode }) {
  return (
    <a className="hcard hcard-link" href={to} aria-label={label}>
      {children}
    </a>
  )
}

// ---------------------------------------------------------------------
// 카드들
// ---------------------------------------------------------------------

function AssetsCard({
  count,
  totals,
  quotesStatus,
  alertHits,
}: {
  count: number
  totals: PortfolioTotals
  quotesStatus: Status
  alertHits: AlertRow[]
}) {
  const to = hashOf('assets')
  if (count === 0) {
    return (
      <LinkCard to={to} label="내 자산으로">
        <Row
          icon={<Icon name="wallet" tone="green" />}
          value="보유 종목을 등록해 보세요"
          sub="평가손익 · 자산 추이 · 목표가 알림을 볼 수 있어요"
          right={<span className="pill pill-blue">등록하기</span>}
        />
      </LinkCard>
    )
  }

  // 시세가 아직 안 왔으면(첫 호출 중) 0원을 보여 주지 않는다
  const status: Status = totals.value > 0 ? 'ready' : quotesStatus
  const pnlDir = direction(totals.pnl)
  const dayDir = direction(totals.dayPnl)
  return (
    <LinkCard to={to} label="내 자산으로">
      <Row
        icon={<Icon name="wallet" tone="green" />}
        value={
          <Value status={status}>
            <span className="mono">{formatWon(totals.value)}원</span>
          </Value>
        }
        sub={
          <>
            내 자산
            {status === 'ready' && (
              <>
                {' · '}
                <span className={`mono dir-${pnlDir}`}>
                  {formatSigned(totals.pnl)}원 ({formatPct(totals.returnPct)})
                </span>
              </>
            )}
          </>
        }
        right={
          status === 'ready' ? (
            <span className="pill">
              전일 <span className={`mono dir-${dayDir}`}>{formatSigned(totals.dayPnl)}원</span>
            </span>
          ) : undefined
        }
      />
      {alertHits.length > 0 && (
        <p className="hnote">
          <span className="hnote-dot" aria-hidden="true" />
          목표가·손절가 도달 {alertHits.length}건 ·{' '}
          {alertHits
            .map((r) => `${r.name} ${r.status?.kind === 'target-hit' ? '목표가' : '손절가'}`)
            .join(', ')}
        </p>
      )}
      <div className="hcard-foot">
        자산 추이 · 목표가 알림 보기 <Chevron />
      </div>
    </LinkCard>
  )
}

function SignalsCard({
  signals,
  status,
  day,
  onRetry,
}: {
  signals: Signal[]
  status: Status
  day?: string | null
  onRetry: () => void
}) {
  const neg = signals.filter((s) => s.type.includes('neg')).length
  let maxSev: Severity | null = null
  for (const s of signals) if (!maxSev || SEV_RANK[s.severity] > SEV_RANK[maxSev]) maxSev = s.severity

  return (
    <section className="hcard" aria-label="오늘의 시그널">
      <Row
        icon={<Icon name="bell" tone="blue" />}
        value={<Value status={status}>시그널 {signals.length}건</Value>}
        sub={
          status === 'error' ? (
            <button type="button" className="hretry" onClick={onRetry}>
              다시 시도
            </button>
          ) : status === 'loading' ? (
            '오늘의 시그널'
          ) : signals.length === 0 ? (
            '오늘은 감정이 크게 바뀐 종목이 없어요'
          ) : (
            `${day ? `${formatKoDate(day)} 기준 · ` : ''}뉴스 감정이 크게 바뀐 종목`
          )
        }
        right={
          status === 'ready' && signals.length > 0 ? (
            neg > 0 ? (
              <span className="pill pill-blue">급락 {neg}건</span>
            ) : maxSev ? (
              <span className="pill">심각도 {SEV_LABEL[maxSev]}</span>
            ) : undefined
          ) : undefined
        }
      />
      {status === 'ready' && signals.length > 0 && (
        <ul className="hlist">
          {signals.map((s, i) => {
            const name = s.name ?? s.symbol ?? '-'
            const pos = s.type === 'sentiment_surge_pos'
            const delta = typeof s.evidence?.delta === 'number' ? (s.evidence.delta as number) : null
            const n = typeof s.evidence?.news_count === 'number' ? (s.evidence.news_count as number) : null
            return (
              <li key={`${s.symbol}-${s.type}-${i}`} className="hitem">
                <StockAvatar name={name} size="sm" />
                <div className="hitem-main">
                  <span className="hitem-name">{name}</span>
                  <span className="hitem-sub">
                    <span className={pos ? 'dir-up' : 'dir-down'}>
                      {pos ? '감정 급등' : '감정 급락'}
                    </span>
                    {delta !== null && ` · 변화 ${delta > 0 ? '+' : ''}${delta.toFixed(2)}`}
                    {n !== null && ` · 기사 ${n}건`}
                  </span>
                </div>
                <span className={`pill pill-sev sev-${s.severity}`}>{SEV_LABEL[s.severity]}</span>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

function NewsCard({ news, status }: { news: NewsItem[]; status: Status }) {
  const { good, bad } = countTones(news)
  return (
    <LinkCard to={hashOf('news')} label="뉴스로">
      <Row
        icon={<Icon name="paper" tone="orange" />}
        value={
          <Value status={status}>
            <span className="dir-up">호재 {good}</span>
            <span className="hsep"> · </span>
            <span className="dir-down">악재 {bad}</span>
          </Value>
        }
        sub={status === 'ready' ? `주요 뉴스 ${news.length}건 · 감정이 강한 순` : '오늘의 주요 뉴스'}
        right={status === 'ready' ? <span className="pill pill-blue">전체 보기</span> : undefined}
      />
      {status === 'ready' && news.length > 0 && (
        <ul className="hlist">
          {news.slice(0, 2).map((n, i) => {
            const t = newsTone(n.sentiment)
            return (
              <li key={`${n.url ?? n.title}-${i}`} className="hnews">
                <span className={`hnews-tone news-score ${t.cls}`}>{t.label}</span>
                <span className="hnews-title">{n.title}</span>
              </li>
            )
          })}
        </ul>
      )}
    </LinkCard>
  )
}

function MoversCard({
  movers,
  status,
  tickerCount,
}: {
  movers: Movers | null
  status: Status
  tickerCount: number
}) {
  // 오른 쪽·내린 쪽을 섞어 크게 움직인 순으로 — 한 줄 목록이라 두 칸으로 나누지 않는다
  const all: Mover[] = [...(movers?.gainers ?? []), ...(movers?.losers ?? [])]
    .filter((m) => m.change_pct != null)
    .sort((a, b) => Math.abs(b.change_pct ?? 0) - Math.abs(a.change_pct ?? 0))
  const top = all[0]
  const topDir = direction(top?.change_pct)

  return (
    <LinkCard to={hashOf('chart')} label="종목 차트로">
      <Row
        icon={<Icon name="chart" tone="purple" />}
        value={
          <Value status={status}>
            {top ? (
              <>
                {top.name}{' '}
                <span className={`mono dir-${topDir}`}>{formatPct(top.change_pct)}</span>
              </>
            ) : (
              '시세 데이터 없음'
            )}
          </Value>
        }
        sub={
          status === 'ready'
            ? `가장 크게 움직인 종목${tickerCount ? ` · 추적 ${tickerCount}종목` : ''}${
                movers?.date ? ` · ${formatKoDate(movers.date)} 종가` : ''
              }`
            : '급등락 종목'
        }
        right={<Chevron />}
      />
      {status === 'ready' && all.length > 1 && (
        <ul className="hlist">
          {all.slice(1, MOVER_ROWS + 1).map((m) => {
            const d = direction(m.change_pct)
            return (
              <li key={m.symbol} className="hitem">
                <StockAvatar name={m.name} size="sm" />
                <div className="hitem-main">
                  <span className="hitem-name">{m.name}</span>
                  <span className="hitem-sub mono">
                    {m.close != null ? `${m.close.toLocaleString('ko-KR')}원` : '—'}
                  </span>
                </div>
                <span className={`hitem-pct mono dir-${d}`}>{formatPct(m.change_pct)}</span>
              </li>
            )
          })}
        </ul>
      )}
    </LinkCard>
  )
}

function ReportCard({ date, status }: { date?: string | null; status: Status }) {
  return (
    <LinkCard to={hashOf('report')} label="리포트로">
      <Row
        icon={<Icon name="report" tone="teal" />}
        value={<Value status={status}>{date ? `${formatKoDate(date)} 브리핑` : '리포트 없음'}</Value>}
        sub="AI가 정리한 직전 장 마감과 밤사이 뉴스"
        right={status === 'ready' && date ? <span className="pill">읽기</span> : undefined}
      />
    </LinkCard>
  )
}

export function Home(props: {
  holdingsCount: number
  totals: PortfolioTotals
  quotesStatus: Status
  alertHits: AlertRow[]
  signals: Signal[]
  signalsStatus: Status
  signalDay?: string | null
  news: NewsItem[]
  newsStatus: Status
  movers: Movers | null
  moversStatus: Status
  tickerCount: number
  reportDate?: string | null
  reportStatus: Status
  onRetry: () => void
}) {
  return (
    <div className="home">
      <AssetsCard
        count={props.holdingsCount}
        totals={props.totals}
        quotesStatus={props.quotesStatus}
        alertHits={props.alertHits}
      />
      <SignalsCard
        signals={props.signals}
        status={props.signalsStatus}
        day={props.signalDay}
        onRetry={props.onRetry}
      />
      <NewsCard news={props.news} status={props.newsStatus} />
      <MoversCard movers={props.movers} status={props.moversStatus} tickerCount={props.tickerCount} />
      <ReportCard date={props.reportDate} status={props.reportStatus} />
    </div>
  )
}
