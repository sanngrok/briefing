import { useEffect, useState } from 'react'
import { api } from './api/client'
import type { Report, Signal, TickerMetrics } from './api/client'
import { DisclaimerBadge } from './components/DisclaimerBadge'
import { SignalCard } from './components/SignalCard'
import { SentimentChart } from './components/SentimentChart'
import { ReportView } from './components/ReportView'

const TICKERS = [
  { symbol: '005930', name: '삼성전자' },
  { symbol: '000660', name: 'SK하이닉스' },
  { symbol: '035420', name: 'NAVER' },
  { symbol: '035720', name: '카카오' },
]

export default function App() {
  const [report, setReport] = useState<Report | null>(null)
  const [signals, setSignals] = useState<Signal[]>([])
  const [metrics, setMetrics] = useState<TickerMetrics | null>(null)
  const [symbol, setSymbol] = useState(TICKERS[0].symbol)
  const [loadError, setLoadError] = useState(false)

  useEffect(() => {
    api.latestReport().then(setReport).catch(() => setReport(null))
    api.signals().then(setSignals).catch(() => setSignals([]))
  }, [])

  useEffect(() => {
    setLoadError(false)
    api
      .metrics(symbol)
      .then(setMetrics)
      .catch(() => {
        setMetrics(null)
        setLoadError(true)
      })
  }, [symbol])

  return (
    <div className="app">
      <header className="header">
        <h1>AI 시그널 리포트</h1>
        <DisclaimerBadge />
      </header>

      <section className="section">
        <h2>오늘의 시그널</h2>
        {signals.length === 0 ? (
          <p className="empty">발화된 감정 급변 시그널이 없습니다.</p>
        ) : (
          <div className="cards">
            {signals.map((s, i) => (
              <SignalCard key={`${s.symbol}-${s.type}-${i}`} signal={s} />
            ))}
          </div>
        )}
      </section>

      <section className="section">
        <h2>종목 추이 (종가 · 평균 감정)</h2>
        <div className="tabs">
          {TICKERS.map((t) => (
            <button
              key={t.symbol}
              className={t.symbol === symbol ? 'tab active' : 'tab'}
              onClick={() => setSymbol(t.symbol)}
            >
              {t.name}
            </button>
          ))}
        </div>
        {loadError && (
          <p className="empty">데이터를 불러오지 못했습니다. (API 연결을 확인하세요)</p>
        )}
        <SentimentChart data={metrics?.series ?? []} />
      </section>

      <section className="section">
        <h2>일일 리포트</h2>
        <ReportView report={report} />
      </section>

      <footer className="footer">
        <DisclaimerBadge />
      </footer>
    </div>
  )
}
