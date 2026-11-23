import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api/client'
import type { Movers, Quote, Report, Signal, Ticker, TickerMetrics } from './api/client'
import { LoadState } from './components/LoadState'
import type { Status } from './components/LoadState'
import { SummaryStrip } from './components/SummaryStrip'
import { SignalCard } from './components/SignalCard'
import { SentimentChart } from './components/SentimentChart'
import { MoversPanel } from './components/MoversPanel'
import { NewsList, NEWS_SHOWN } from './components/NewsList'
import type { NewsLists } from './components/NewsList'
import { ReportView } from './components/ReportView'
import { PortfolioPanel } from './components/PortfolioPanel'
import { SideNav } from './components/SideNav'
import { StockAvatar } from './components/StockAvatar'
import { computeRows, computeTotals, loadHoldings, saveHoldings } from './lib/portfolio'
import { kstDate, loadHistory, mergeHistory, recordSnapshot, saveHistory } from './lib/history'
import type { Snapshot } from './lib/history'
import {
  NOTIFIED_KEY,
  buildAlertRows,
  formatAlertPrice,
  isHit,
  loadAlerts,
  notifyKey,
  pruneNotified,
  saveAlerts,
} from './lib/alerts'
import type { Alerts } from './lib/alerts'
import type { NotifyPermission } from './components/PriceAlerts'
import type { Holding } from './lib/portfolio'
import { isMarketLiveWindow, isUsMarketWindow, isWorldSymbol } from './lib/market'
import { metaOf, pageFromHash } from './lib/route'
import { signalsOfDay } from './lib/signals'
import type { Page } from './lib/route'

/** 첫 화면을 채우는 호출들. 각각 따로 실패할 수 있어 상태도 따로 든다. */
type CoreKey = 'tickers' | 'report' | 'signals' | 'news' | 'movers'

const ALL_LOADING: Record<CoreKey, Status> = {
  tickers: 'loading',
  report: 'loading',
  signals: 'loading',
  news: 'loading',
  movers: 'loading',
}

// 장중엔 15초마다 새로 부른다(서버가 네이버 실시간 값을 덮어써 주므로).
const QUOTE_POLL_MS = 15000
// 장 시간 밖이거나 탭이 가려져 있으면 요청을 보내지 않고, 이 간격으로 조건만 다시 본다.
// 네트워크 호출이 아니라 조건 확인이라 서버에는 아무것도 가지 않는다.
const QUOTE_IDLE_RECHECK_MS = 60000

/** 지금 해시가 가리키는 화면. 뒤로가기·링크로 해시가 바뀌면 따라 바뀐다. */
function useHashPage(): Page {
  const [page, setPage] = useState<Page>(() => pageFromHash(window.location.hash))
  useEffect(() => {
    function onHashChange() {
      setPage(pageFromHash(window.location.hash))
      // 화면을 바꿨는데 이전 화면의 스크롤 위치에 머물면 새 화면 중간부터 보인다.
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])
  return page
}

export default function App() {
  // 화면은 메뉴로 나눴지만 데이터는 여기서 한 번에 불러 둔다. 메뉴를 옮길 때마다
  // 다시 부르면 Render 무료 인스턴스 특성상 화면마다 로딩을 기다리게 된다.
  const page = useHashPage()
  const meta = metaOf(page)
  useEffect(() => {
    document.title = page === 'home' ? 'AI 시그널 리포트' : `${meta.label} · AI 시그널 리포트`
  }, [page, meta.label])

  const [tickers, setTickers] = useState<Ticker[]>([])
  const [report, setReport] = useState<Report | null>(null)
  // 전체 이력으로 받아서 리포트 날짜 하루치만 화면에 쓴다(signalsOfDay 참고).
  const [allSignals, setAllSignals] = useState<Signal[]>([])
  // 방향별로 따로 받는다. 전체를 |감정| 순으로 줄 세운 뒤 자르면 수가 많은 쪽
  // (대개 호재)이 상위를 쓸어가서 악재 탭이 비다시피 하기 때문이다.
  const [news, setNews] = useState<NewsLists>({ all: [], good: [], bad: [] })
  const [movers, setMovers] = useState<Movers | null>(null)
  const [metrics, setMetrics] = useState<TickerMetrics | null>(null)
  const [symbol, setSymbol] = useState('')

  // 로딩·실패·빈 결과를 화면에서 구분하기 위한 상태. 예전에는 실패하면 조용히
  // 빈 값을 넣어서, API 가 죽어도 "시그널이 없습니다"라고 말했다.
  const [coreStatus, setCoreStatus] = useState<Record<CoreKey, Status>>(ALL_LOADING)
  const [metricsStatus, setMetricsStatus] = useState<Status>('loading')
  const [quotesStatus, setQuotesStatus] = useState<Status>('loading')

  // 내 포트폴리오: 개인 매매 정보라 서버에 보내지 않고 이 브라우저에만 둔다.
  const [holdings, setHoldings] = useState<Holding[]>(() => loadHoldings())
  const [quotes, setQuotes] = useState<Quote[]>([])
  const [quoteDate, setQuoteDate] = useState<string | null>(null)
  const [quotesLive, setQuotesLive] = useState(false)
  // USD 보유 종목의 평단을 현재 환율로 환산하는 데 쓴다(수익률에서 환율 약분).
  const [fxUsdKrw, setFxUsdKrw] = useState<number | null>(null)
  const [storageFailed, setStorageFailed] = useState(false)

  // 해외 종목을 들고 있을 때만 미국 장 시간(한국 새벽)에도 폴링한다.
  // 폴링 루프가 effect 안에 갇혀 있어 최신 값을 ref 로 건넨다.
  const hasWorldHoldingRef = useRef(false)
  useEffect(() => {
    hasWorldHoldingRef.current = holdings.some((h) => isWorldSymbol(h.symbol))
  }, [holdings])

  // 시세를 물을 종목 목록. 보유 종목을 지정해야 워치리스트 밖 종목과 해외 종목도
  // 시세가 붙는다(종목을 안 주면 서버가 워치리스트만 돌려준다). 수량·평단만
  // 고친 경우에는 목록이 그대로라 폴링을 다시 시작하지 않도록 문자열로 묶는다.
  const symbolsKey = useMemo(
    () => [...new Set(holdings.map((h) => h.symbol))].sort().join(','),
    [holdings],
  )

  function updateHoldings(next: Holding[]) {
    setHoldings(next)
    setStorageFailed(!saveHoldings(next))
  }

  // 자산 추이(하루 한 점)와 목표가·손절가. 보유 목록처럼 이 브라우저에만 둔다.
  const [history, setHistory] = useState<Snapshot[]>(() => loadHistory())
  const [alerts, setAlerts] = useState<Alerts>(() => loadAlerts())
  const [notifyPermission, setNotifyPermission] = useState<NotifyPermission>(() =>
    typeof Notification === 'undefined' ? 'unsupported' : Notification.permission,
  )

  function updateAlerts(next: Alerts) {
    setAlerts(next)
    if (!saveAlerts(next)) setStorageFailed(true)
  }

  function importExtras(extras: { history: Snapshot[]; alerts: Alerts }) {
    if (extras.history.length) {
      setHistory((prev) => {
        const next = mergeHistory(prev, extras.history)
        saveHistory(next)
        return next
      })
    }
    if (Object.keys(extras.alerts).length) updateAlerts({ ...alerts, ...extras.alerts })
  }

  function enableNotify() {
    if (typeof Notification === 'undefined') return
    Notification.requestPermission().then(setNotifyPermission).catch(() => {})
  }

  // 워치리스트는 서버가 가진 것을 그대로 따른다(프론트 하드코딩 금지).
  //
  // 다섯 호출을 한 함수로 묶어 둔 건 "다시 시도" 버튼이 같은 일을 다시 해야 하기
  // 때문이다. 상태는 호출별로 따로 세워서, 하나가 죽어도 나머지 섹션은 정상으로
  // 보이게 한다.
  const loadCore = useCallback(() => {
    setCoreStatus(ALL_LOADING)

    function mark(key: CoreKey, status: Status) {
      setCoreStatus((prev) => ({ ...prev, [key]: status }))
    }

    api
      .tickers()
      .then((list) => {
        setTickers(list)
        // 이미 고른 종목은 유지한다 — 재시도로 차트 탭이 첫 종목으로 튀지 않게.
        if (list.length > 0) setSymbol((prev) => prev || list[0].symbol)
        mark('tickers', 'ready')
      })
      .catch(() => {
        setTickers([])
        mark('tickers', 'error')
      })

    api
      .latestReport()
      .then((r) => {
        setReport(r)
        mark('report', 'ready')
      })
      .catch(() => {
        setReport(null)
        mark('report', 'error')
      })

    api
      .signals()
      .then((s) => {
        setAllSignals(s)
        mark('signals', 'ready')
      })
      .catch(() => {
        setAllSignals([])
        mark('signals', 'error')
      })

    Promise.all([
      api.news({ limit: NEWS_SHOWN }),
      api.news({ limit: NEWS_SHOWN, direction: 'good' }),
      api.news({ limit: NEWS_SHOWN, direction: 'bad' }),
    ])
      .then(([all, good, bad]) => {
        setNews({ all, good, bad })
        mark('news', 'ready')
      })
      .catch(() => {
        setNews({ all: [], good: [], bad: [] })
        mark('news', 'error')
      })

    api
      .movers({ limit: 5 })
      .then((m) => {
        setMovers(m)
        mark('movers', 'ready')
      })
      .catch(() => {
        setMovers(null)
        mark('movers', 'error')
      })
  }, [])

  useEffect(() => {
    loadCore()
  }, [loadCore])

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
      // 보유 종목이 없으면 종목을 지정하지 않는다 — 워치리스트 기준일이라도
      // 받아 와야 화면 하단의 "OOOO 종가 기준" 표시가 비지 않는다.
      const symbols = symbolsKey ? symbolsKey.split(',') : undefined
      api
        .quotes(symbols ? { symbols } : undefined)
        .then((q) => {
          if (cancelled) return
          setQuotes(q.quotes)
          setQuoteDate(q.date ?? null)
          setQuotesLive(q.live ?? false)
          setFxUsdKrw(q.fx_usdkrw ?? null)
          setQuotesStatus('ready')
        })
        .catch(() => {
          if (cancelled) return
          setQuotes([])
          setQuotesStatus('error')
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
  }, [symbolsKey])

  const loadMetrics = useCallback(() => {
    if (!symbol) return
    setMetricsStatus('loading')
    api
      .metrics(symbol)
      .then((m) => {
        setMetrics(m)
        setMetricsStatus('ready')
      })
      .catch(() => {
        setMetrics(null)
        setMetricsStatus('error')
      })
  }, [symbol])

  useEffect(() => {
    loadMetrics()
  }, [loadMetrics])

  // 차트 위 요약: 가장 최근 종가와 등락률 (국내 관행 = 상승 빨강 / 하락 파랑)
  const last = metrics?.series?.[metrics.series.length - 1]
  const change = last?.change_pct ?? null
  const dir = change === null ? 'flat' : change > 0 ? 'up' : change < 0 ? 'down' : 'flat'

  const signals = useMemo(() => signalsOfDay(allSignals, report?.date), [allSignals, report])

  // 평가는 화면(내 자산)뿐 아니라 자산 기록·목표가 판정·배지에도 쓰여 여기서 한 번 한다.
  const pfRows = useMemo(() => computeRows(holdings, quotes, fxUsdKrw), [holdings, quotes, fxUsdKrw])
  const alertRows = useMemo(() => buildAlertRows(pfRows, alerts, fxUsdKrw), [pfRows, alerts, fxUsdKrw])
  const alertHits = useMemo(
    () => alertRows.filter((r) => r.status && isHit(r.status.kind)),
    [alertRows],
  )

  // 오늘 총 평가금액을 기록한다(어느 메뉴에 있든). 시세가 안 붙은 종목이 하나라도
  // 있으면 합계가 덜 잡혀 그래프가 꺾이므로 건너뛴다 — 보유 종목을 바꾼 직후,
  // 새 시세가 오기 전의 한순간도 여기서 걸러진다.
  useEffect(() => {
    if (quotesStatus !== 'ready' || pfRows.length === 0) return
    const totals = computeTotals(pfRows)
    if (totals.unpricedCount > 0 || totals.value <= 0) return
    const snap = {
      date: kstDate(),
      value: totals.value,
      cost: totals.pricedCost,
      at: new Date().toISOString(),
    }
    setHistory((prev) => {
      const next = recordSnapshot(prev, snap)
      if (next !== prev) saveHistory(next)
      return next
    })
  }, [pfRows, quotesStatus])

  // 목표가·손절가에 닿으면 브라우저 알림. 같은 종목·같은 종류는 하루 한 번만.
  // 사이트가 열려 있을 때만 동작한다(장중 15초 폴링에 맞춰 판정된다).
  useEffect(() => {
    if (notifyPermission !== 'granted' || alertHits.length === 0) return
    const today = kstDate()
    let sent: string[] = []
    try {
      sent = pruneNotified(JSON.parse(window.localStorage.getItem(NOTIFIED_KEY) ?? '[]'), today)
    } catch {
      sent = []
    }
    let changed = false
    for (const r of alertHits) {
      const kind = r.status!.kind
      const key = notifyKey(today, r.symbol, kind)
      if (sent.includes(key)) continue
      const target = kind === 'target-hit'
      const line = target
        ? `목표가 ${formatAlertPrice(r.setting?.target, r.currency)}`
        : `손절가 ${formatAlertPrice(r.setting?.stop, r.currency)}`
      try {
        new Notification(`${r.name} ${target ? '목표가' : '손절가'} 도달`, {
          body: `현재 ${formatAlertPrice(r.price, r.currency)} · ${line}`,
          tag: key,
        })
      } catch {
        // 일부 모바일 브라우저는 페이지에서 직접 만든 알림을 막는다 — 화면 표시로 충분하다
      }
      sent.push(key)
      changed = true
    }
    if (changed) {
      try {
        window.localStorage.setItem(NOTIFIED_KEY, JSON.stringify(sent))
      } catch {
        /* 저장 못 하면 다음 판정에 한 번 더 뜰 뿐 */
      }
    }
  }, [alertHits, notifyPermission])

  // 메뉴 배지: 오늘 시그널 수 / 내 자산은 보유 종목에 걸린 시그널 + 목표가·손절가 도달
  const heldSymbols = useMemo(() => new Set(holdings.map((h) => h.symbol)), [holdings])
  const heldSignalCount =
    coreStatus.signals === 'ready'
      ? signals.filter((s) => s.symbol != null && heldSymbols.has(s.symbol)).length
      : 0
  const badges = {
    ...(coreStatus.signals === 'ready' ? { home: signals.length } : {}),
    assets: heldSignalCount + alertHits.length,
  }

  return (
    <div className="layout">
      <SideNav page={page} reportDate={report?.date} badges={badges} />

      {/* key 로 화면이 바뀔 때마다 새로 그려 살짝 떠오르는 전환을 준다 */}
      <main className="content" key={page}>
        <header className="page-head">
          <h1 className="page-title">{meta.title}</h1>
          <p className="page-desc">{meta.desc}</p>
        </header>

        {page === 'home' && (
          <>
            <SummaryStrip
              signals={signals}
              tickerCount={tickers.length}
              newsCount={news.all.length}
              status={coreStatus}
            />

            <section className="section">
              <h2 className="section-title">
                오늘의 시그널
                {signals[0] && <span className="section-hint mono">{signals[0].date} 기준</span>}
              </h2>
              {coreStatus.signals !== 'ready' ? (
                <LoadState
                  status={coreStatus.signals}
                  rows={4}
                  onRetry={loadCore}
                  label="시그널을 불러오지 못했습니다."
                />
              ) : signals.length === 0 ? (
                <p className="empty">
                  오늘은 감정이 크게 바뀐 종목이 없어요. 기준선보다 큰 변화가 잡히면 여기에
                  보여 드릴게요.
                </p>
              ) : (
                <div className="signal-grid">
                  {signals.map((s, i) => (
                    <SignalCard key={`${s.symbol}-${s.type}-${i}`} signal={s} />
                  ))}
                </div>
              )}
            </section>

            <section className="section">
              <h2 className="section-title">
                급등락 종목
                <span className="section-hint">워치리스트 등락률 상위 · ±5% 이상은 급등락 표시</span>
              </h2>
              <MoversPanel movers={movers} status={coreStatus.movers} onRetry={loadCore} />
            </section>
          </>
        )}

        {page === 'assets' && (
          <PortfolioPanel
            holdings={holdings}
            onChange={updateHoldings}
            quotes={quotes}
            quoteDate={quoteDate}
            quotesLive={quotesLive}
            fxUsdKrw={fxUsdKrw}
            tickers={tickers}
            signals={signals}
            storageFailed={storageFailed}
            quotesStatus={quotesStatus}
            history={history}
            today={kstDate()}
            alerts={alerts}
            onAlertsChange={updateAlerts}
            alertRows={alertRows}
            notifyPermission={notifyPermission}
            onEnableNotify={enableNotify}
            onImportExtras={importExtras}
          />
        )}

        {page === 'news' && (
          <div className="panel panel-flush">
            <NewsList lists={news} status={coreStatus.news} onRetry={loadCore} />
          </div>
        )}

        {page === 'chart' &&
          // 종목 목록이 없으면 고를 탭도, 부를 차트도 없다 — 여기서 먼저 끊는다.
          // 그러지 않으면 symbol 이 비어 metrics 가 영원히 'loading' 에 머문다.
          (coreStatus.tickers !== 'ready' ? (
            <LoadState
              status={coreStatus.tickers}
              rows={5}
              onRetry={loadCore}
              label="종목 목록을 불러오지 못했습니다."
            />
          ) : (
            <div className="panel">
              <div className="chips" role="group" aria-label="종목 선택">
                {tickers.map((t) => (
                  <button
                    key={t.symbol}
                    type="button"
                    className={t.symbol === symbol ? 'chip active' : 'chip'}
                    aria-pressed={t.symbol === symbol}
                    onClick={() => setSymbol(t.symbol)}
                  >
                    {t.name}
                  </button>
                ))}
              </div>

              {metrics && last && (
                <div className="quote">
                  <StockAvatar name={metrics.name} size="lg" />
                  <div className="quote-main">
                    <span className="quote-name">{metrics.name}</span>
                    <span className="quote-line">
                      <span className="quote-close mono">
                        {last.close != null ? `${last.close.toLocaleString('ko-KR')}원` : '—'}
                      </span>
                      {change !== null && (
                        <span className={`quote-change mono dir-${dir}`}>
                          {change > 0 ? '+' : change < 0 ? '−' : ''}
                          {Math.abs(change).toFixed(2)}%
                        </span>
                      )}
                    </span>
                  </div>
                  <span className="quote-date mono">{last.date} 종가</span>
                </div>
              )}

              <SentimentChart
                data={metrics?.series ?? []}
                status={metricsStatus}
                onRetry={loadMetrics}
              />
            </div>
          ))}

        {page === 'report' && (
          <ReportView report={report} status={coreStatus.report} onRetry={loadCore} />
        )}
      </main>
    </div>
  )
}
