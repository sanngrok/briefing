import { useEffect, useRef, useState } from 'react'
import { api } from './api/client'
import type { Movers, NewsItem, Quote, Report, Signal, Ticker, TickerMetrics } from './api/client'
import { DisclaimerBadge } from './components/DisclaimerBadge'
import { SummaryStrip } from './components/SummaryStrip'
import { SignalCard } from './components/SignalCard'
import { SentimentChart } from './components/SentimentChart'
import { MoversPanel } from './components/MoversPanel'
import { NewsList } from './components/NewsList'
import { ReportView } from './components/ReportView'
import { PortfolioPanel } from './components/PortfolioPanel'
import { loadHoldings, saveHoldings } from './lib/portfolio'
import type { Holding } from './lib/portfolio'
import { isMarketLiveWindow, isUsMarketWindow, isWorldSymbol } from './lib/market'

// 장중엔 15초마다 새로 부른다(서버가 네이버 실시간 값을 덮어써 주므로).
const QUOTE_POLL_MS = 15000
// 장 시간 밖이거나 탭이 가려져 있으면 요청을 보내지 않고, 이 간격으로 조건만 다시 본다.
// 네트워크 호출이 아니라 조건 확인이라 서버에는 아무것도 가지 않는다.
const QUOTE_IDLE_RECHECK_MS = 60000

export default function App() {
  const [tickers, setTickers] = useState<Ticker[]>([])
  const [report, setReport] = useState<Report | null>(null)
  const [signals, setSignals] = useState<Signal[]>([])
  const [news, setNews] = useState<NewsItem[]>([])
  const [movers, setMovers] = useState<Movers | null>(null)
  const [metrics, setMetrics] = useState<TickerMetrics | null>(null)
  const [symbol, setSymbol] = useState('')
  const [loadError, setLoadError] = useState(false)

  // 내 포트폴리오: 개인 매매 정보라 서버에 보내지 않고 이 브라우저에만 둔다.
  const [holdings, setHoldings] = useState<Holding[]>(() => loadHoldings())
  const [quotes, setQuotes] = useState<Quote[]>([])
  const [quoteDate, setQuoteDate] = useState<string | null>(null)
  const [quotesLive, setQuotesLive] = useState(false)
  const [storageFailed, setStorageFailed] = useState(false)

  // 해외 종목을 들고 있을 때만 미국 장 시간(한국 새벽)에도 폴링한다.
  // 폴링 루프가 effect 안에 갇혀 있어 최신 값을 ref 로 건넨다.
  const hasWorldHoldingRef = useRef(false)
  useEffect(() => {
    hasWorldHoldingRef.current = holdings.some((h) => isWorldSymbol(h.symbol))
  }, [holdings])

  function updateHoldings(next: Holding[]) {
    setHoldings(next)
    setStorageFailed(!saveHoldings(next))
  }

  // 워치리스트는 서버가 가진 것을 그대로 따른다(프론트 하드코딩 금지).
  useEffect(() => {
    api
      .tickers()
      .then((list) => {
        setTickers(list)
        if (list.length > 0) setSymbol(list[0].symbol)
      })
      .catch(() => setTickers([]))
    api.latestReport().then(setReport).catch(() => setReport(null))
    api.signals().then(setSignals).catch(() => setSignals([]))
    api.news({ limit: 12 }).then(setNews).catch(() => setNews([]))
    api.movers({ limit: 5 }).then(setMovers).catch(() => setMovers(null))
  }, [])

  // 포트폴리오 평가용 종가(워치리스트 전체를 한 번에). 장중엔 서버가 네이버
  // 실시간 값을 덮어써 주므로, 여기서 주기적으로 다시 불러오면 "준실시간"이 된다.
  //
  // 다만 장 시간 밖이나 탭이 가려져 있을 때는 부르지 않는다. 그때는 서버가 같은 DB
  // 값을 돌려줄 뿐이라 값이 변하지 않는데, 요청이 계속 가면 무료 인스턴스가 잠들지
  // 못해 쿼터만 쓴다(탭 하나를 하루 종일 열어두면 한 달치를 거의 다 쓴다).
  //
  // 해외 종목을 들고 있으면 미국 정규장(한국 새벽)에도 돈다 — 그때가 해외 종목이
  // 실제로 움직이는 시간이다.
  useEffect(() => {
    let cancelled = false
    let timer: number | undefined

    function loadQuotes() {
      api
        .quotes()
        .then((q) => {
          if (cancelled) return
          setQuotes(q.quotes)
          setQuoteDate(q.date ?? null)
          setQuotesLive(q.live ?? false)
        })
        .catch(() => {
          if (!cancelled) setQuotes([])
        })
    }

    function shouldPoll() {
      if (document.hidden) return false
      if (isMarketLiveWindow()) return true
      return hasWorldHoldingRef.current && isUsMarketWindow()
    }

    function schedule() {
      timer = window.setTimeout(tick, shouldPoll() ? QUOTE_POLL_MS : QUOTE_IDLE_RECHECK_MS)
    }

    function tick() {
      if (cancelled) return
      if (shouldPoll()) loadQuotes()
      schedule()
    }

    // 탭으로 돌아왔을 때 다음 틱까지 기다리지 않고 바로 최신화한다.
    function onVisibilityChange() {
      if (shouldPoll()) loadQuotes()
    }

    loadQuotes() // 최초 1회는 장 시간 밖이어도 부른다(전일 종가를 보여줘야 하므로)
    schedule()
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => {
      cancelled = true
      if (timer !== undefined) window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [])

  useEffect(() => {
    if (!symbol) return
    setLoadError(false)
    api
      .metrics(symbol)
      .then(setMetrics)
      .catch(() => {
        setMetrics(null)
        setLoadError(true)
      })
  }, [symbol])

  // 차트 위 요약: 가장 최근 종가와 등락률 (국내 관행 = 상승 빨강 / 하락 파랑)
  const last = metrics?.series?.[metrics.series.length - 1]
  const change = last?.change_pct ?? null
  const dir = change === null ? 'flat' : change > 0 ? 'up' : change < 0 ? 'down' : 'flat'

  return (
    <div className="app">
      <header className="header">
        <div className="brand-row">
          <h1 className="title">AI 시그널 리포트</h1>
          {report && <span className="date-pill mono">{report.date}</span>}
        </div>
        <p className="subtitle">국내 주식 뉴스 감정을 매일 분석해 급변 시그널을 찾습니다.</p>
        <DisclaimerBadge />
        <SummaryStrip signals={signals} tickerCount={tickers.length} newsCount={news.length} />
      </header>

      <section className="section">
        <h2 className="section-title">
          내 포트폴리오
          <span className="section-hint">이 브라우저에만 저장 · 서버로 전송되지 않음</span>
        </h2>
        <PortfolioPanel
          holdings={holdings}
          onChange={updateHoldings}
          quotes={quotes}
          quoteDate={quoteDate}
          quotesLive={quotesLive}
          tickers={tickers}
          signals={signals}
          storageFailed={storageFailed}
        />
      </section>

      <section className="section">
        <h2 className="section-title">
          급등락 종목
          <span className="section-hint">워치리스트 등락률 상위 · ±5% 이상은 급등락 표시</span>
        </h2>
        <MoversPanel movers={movers} />
      </section>

      <section className="section">
        <h2 className="section-title">오늘의 시그널</h2>
        {signals.length === 0 ? (
          <p className="empty">
            발화된 감정 급변 시그널이 없습니다. 감정 기준선 대비 큰 변화가 잡히면 여기에 표시됩니다.
          </p>
        ) : (
          <div className="signal-grid">
            {signals.map((s, i) => (
              <SignalCard key={`${s.symbol}-${s.type}-${i}`} signal={s} />
            ))}
          </div>
        )}

        <h3 className="subsection-title">
          주요 뉴스
          <span className="subsection-hint">감정 강도가 큰 순</span>
        </h3>
        <div className="panel panel-flush">
          <NewsList items={news} />
        </div>
      </section>

      <section className="section">
        <h2 className="section-title">종목 추이 (종가 · 평균 감정)</h2>
        <div className="panel">
          <div className="tabs">
            {tickers.map((t) => (
              <button
                key={t.symbol}
                className={t.symbol === symbol ? 'tab active' : 'tab'}
                onClick={() => setSymbol(t.symbol)}
              >
                {t.name}
              </button>
            ))}
          </div>

          {metrics && last && (
            <div className="quote">
              <span className="quote-name">{metrics.name}</span>
              <span className="quote-close mono">
                {last.close != null ? last.close.toLocaleString('ko-KR') : '—'}
              </span>
              {change !== null && (
                <span className={`quote-change mono dir-${dir}`}>
                  {change > 0 ? '▲' : change < 0 ? '▼' : '—'} {Math.abs(change).toFixed(2)}%
                </span>
              )}
              <span className="quote-date mono">{last.date}</span>
            </div>
          )}

          {loadError && (
            <p className="empty">데이터를 불러오지 못했습니다. (API 연결을 확인하세요)</p>
          )}
          <SentimentChart data={metrics?.series ?? []} />
        </div>
      </section>

      <section className="section">
        <h2 className="section-title">일일 리포트</h2>
        <ReportView report={report} />
      </section>

      <footer className="footer">
        <DisclaimerBadge />
      </footer>
    </div>
  )
}
