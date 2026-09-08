import { useEffect, useState } from 'react'
import { api } from './api/client'
import type { NewsItem, Report, Signal, Ticker, TickerMetrics } from './api/client'
import { DisclaimerBadge } from './components/DisclaimerBadge'
import { SummaryStrip } from './components/SummaryStrip'
import { SignalCard } from './components/SignalCard'
import { SentimentChart } from './components/SentimentChart'
import { NewsList } from './components/NewsList'
import { ReportView } from './components/ReportView'

export default function App() {
  const [tickers, setTickers] = useState<Ticker[]>([])
  const [report, setReport] = useState<Report | null>(null)
  const [signals, setSignals] = useState<Signal[]>([])
  const [news, setNews] = useState<NewsItem[]>([])
  const [metrics, setMetrics] = useState<TickerMetrics | null>(null)
  const [symbol, setSymbol] = useState('')
  const [loadError, setLoadError] = useState(false)

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
