import { useMemo, useRef, useState } from 'react'
import type { Quote, Signal, Ticker } from '../api/client'
import {
  computeRows,
  computeTotals,
  direction,
  findDuplicate,
  formatPct,
  formatSigned,
  formatWon,
  mergeHolding,
  newId,
  normalizeSymbol,
  parseHoldings,
  serializeHoldings,
  sortByReturn,
  validateHolding,
} from '../lib/portfolio'
import type { Holding, HoldingInput, HoldingRow } from '../lib/portfolio'
import type { Status } from './LoadState'
import { StockAvatar } from './StockAvatar'
import { PortfolioHistory } from './PortfolioHistory'
import { PriceAlerts } from './PriceAlerts'
import type { NotifyPermission } from './PriceAlerts'
import { parseHistory } from '../lib/history'
import type { Snapshot } from '../lib/history'
import { parseAlerts } from '../lib/alerts'
import type { AlertRow, Alerts } from '../lib/alerts'

const EMPTY_FORM: HoldingInput = { symbol: '', name: '', quantity: '', avgPrice: '', memo: '' }

interface Props {
  holdings: Holding[]
  onChange: (next: Holding[]) => void
  quotes: Quote[]
  /** 현재 원/달러 환율 — USD 보유 종목을 원화로 환산할 때 쓴다. */
  fxUsdKrw?: number | null
  quoteDate?: string | null
  quotesLive?: boolean
  tickers: Ticker[]
  signals: Signal[]
  storageFailed?: boolean
  /** 시세 호출 상태. 실패를 "시세 없음"으로 뭉개지 않기 위해 따로 받는다. */
  quotesStatus?: Status
  /** 자산 추이 (하루 한 점) */
  history: Snapshot[]
  /** 오늘 KST 날짜 — 기간 자르기 기준 */
  today: string
  alerts: Alerts
  onAlertsChange: (next: Alerts) => void
  /** App 이 판정까지 끝낸 목표가·손절가 줄 (배지·브라우저 알림과 같은 결과) */
  alertRows: AlertRow[]
  notifyPermission: NotifyPermission
  onEnableNotify: () => void
  /** 가져오기 파일에 들어 있던 자산 추이·알림 설정을 합친다 */
  onImportExtras: (extras: { history: Snapshot[]; alerts: Alerts }) => void
}

export function PortfolioPanel({
  holdings,
  onChange,
  quotes,
  fxUsdKrw,
  quoteDate,
  quotesLive,
  tickers,
  signals,
  storageFailed,
  quotesStatus = 'ready',
  history,
  today,
  alerts,
  onAlertsChange,
  alertRows,
  notifyPermission,
  onEnableNotify,
  onImportExtras,
}: Props) {
  const [form, setForm] = useState<HoldingInput>(EMPTY_FORM)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  // 입력 폼은 평소엔 접어 둔다 — 자주 보는 건 평가금액이지 입력칸이 아니다.
  // 보유 종목이 하나도 없을 때와 수정 중일 때는 펼친다.
  const [formOpen, setFormOpen] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const formRef = useRef<HTMLFormElement>(null)
  const showForm = formOpen || editingId !== null || holdings.length === 0

  const rows = useMemo(
    () => sortByReturn(computeRows(holdings, quotes, fxUsdKrw)),
    [holdings, quotes, fxUsdKrw],
  )
  const totals = useMemo(() => computeTotals(rows), [rows])

  // 보유 종목에 걸린 시그널 — 심각도가 가장 높은 것 하나를 배지로 보여준다.
  const signalBySymbol = useMemo(() => {
    const rank = { high: 3, mid: 2, low: 1 } as const
    const map = new Map<string, Signal>()
    for (const s of signals ?? []) {
      if (!s.symbol) continue
      const key = normalizeSymbol(s.symbol)
      const prev = map.get(key)
      if (!prev || rank[s.severity] > rank[prev.severity]) map.set(key, s)
    }
    return map
  }, [signals])

  const hitSignals = rows.filter((r) => signalBySymbol.has(r.symbol))

  function flash(message: string) {
    setNotice(message)
    setError('')
    window.setTimeout(() => setNotice(''), 4000)
  }

  function resetForm() {
    setForm(EMPTY_FORM)
    setEditingId(null)
    setError('')
  }

  function closeForm() {
    resetForm()
    setFormOpen(false)
  }

  function handleSymbolChange(value: string) {
    // 워치리스트 종목코드를 넣으면 종목명을 자동으로 채운다(직접 입력도 가능).
    const match = tickers.find((t) => t.symbol === normalizeSymbol(value))
    setForm((f) => ({ ...f, symbol: value, name: match ? match.name : f.name }))
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const result = validateHolding(form, editingId ?? newId())
    if (!result.ok) {
      setError(result.error)
      return
    }
    const holding = result.holding
    const duplicate = findDuplicate(holdings, holding.symbol, editingId ?? undefined)

    if (editingId) {
      if (duplicate) {
        setError(`${duplicate.name}(${duplicate.symbol})는 이미 담겨 있습니다.`)
        return
      }
      onChange(holdings.map((h) => (h.id === editingId ? holding : h)))
      flash(`${holding.name} 수정됨`)
    } else if (duplicate) {
      // 같은 종목 재매수 → 수량가중 평단으로 합친다.
      const merged = mergeHolding(duplicate, holding, fxUsdKrw)
      onChange(holdings.map((h) => (h.id === duplicate.id ? merged : h)))
      flash(`${merged.name} 추가 매수로 합산 (평단 ${formatWon(merged.avgPrice)}원)`)
    } else {
      onChange([...holdings, holding])
      flash(`${holding.name} 추가됨`)
    }
    closeForm()
  }

  function handleEdit(row: HoldingRow) {
    setEditingId(row.id)
    setError('')
    setForm({
      symbol: row.symbol,
      name: row.name,
      quantity: String(row.quantity),
      // 직접 입력은 늘 원화다. USD 보유 종목을 수정하면 원화 종목이 된다.
      avgPrice: String(Math.round(row.avgPriceKrw)),
      memo: row.memo ?? '',
    })
    // 폼은 목록 위에 펼쳐진다. 아래쪽 행을 눌렀으면 폼이 화면 밖일 수 있다.
    window.requestAnimationFrame(() => formRef.current?.scrollIntoView({ block: 'nearest' }))
  }

  function handleDelete(row: HoldingRow) {
    if (!window.confirm(`${row.name}(${row.symbol})을(를) 삭제할까요?`)) return
    onChange(holdings.filter((h) => h.id !== row.id))
    if (editingId === row.id) resetForm()
    flash(`${row.name} 삭제됨`)
  }

  function handleExport() {
    const blob = new Blob([serializeHoldings(holdings, new Date(), { history, alerts })], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `portfolio-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''            // 같은 파일을 다시 골라도 change 가 뜨도록
    if (!file) return
    try {
      const json = JSON.parse(await file.text())
      const parsed = parseHoldings(json)
      if (parsed.length === 0) {
        setError('가져올 보유 종목이 없습니다. (형식을 확인하세요)')
        return
      }
      if (
        holdings.length > 0 &&
        !window.confirm(`현재 ${holdings.length}건을 덮어쓰고 ${parsed.length}건을 불러올까요?`)
      )
        return
      onChange(parsed)
      // 자산 추이·알림 설정은 덮어쓰지 않고 합친다 — toss_sync 파일엔 알림이 없다.
      const importedHistory = parseHistory(json)
      onImportExtras({ history: importedHistory, alerts: parseAlerts(json?.alerts ?? null) })
      closeForm()
      flash(
        `${parsed.length}건 불러옴` +
          (importedHistory.length ? ` · 자산 기록 ${importedHistory.length}일 합침` : ''),
      )
    } catch {
      setError('JSON 파일을 읽지 못했습니다.')
    }
  }

  const totalDir = direction(totals.pnl)
  const dayDir = direction(totals.dayPnl)

  return (
    <div className="pf">
      {storageFailed && (
        <p className="pf-warn">
          브라우저 저장소를 쓸 수 없어 새로고침하면 사라져요. (사생활 보호 모드 등)
        </p>
      )}

      {rows.length > 0 && (
        <section className="panel pf-hero" aria-label="평가 요약">
          <div className="pf-hero-label">총 평가금액</div>
          <div className="pf-hero-value mono">
            {formatWon(totals.value)}
            <span className="pf-hero-unit">원</span>
          </div>
          <div className={`pf-hero-pnl mono dir-${totalDir}`}>
            {formatSigned(totals.pnl)}원 ({formatPct(totals.returnPct)})
          </div>

          <dl className="pf-stats">
            <div className="pf-stat">
              <dt>매입금액</dt>
              <dd className="mono">{formatWon(totals.cost)}원</dd>
            </div>
            <div className="pf-stat">
              <dt>전일 대비</dt>
              <dd className={`mono dir-${dayDir}`}>{formatSigned(totals.dayPnl)}원</dd>
            </div>
            <div className="pf-stat">
              <dt>보유 종목</dt>
              <dd className="mono">{rows.length}개</dd>
            </div>
          </dl>
        </section>
      )}

      {rows.length > 0 && <PortfolioHistory history={history} today={today} />}

      {hitSignals.length > 0 && (
        <p className="pf-signal-note">
          <strong>보유 종목 {hitSignals.length}개에 감정 급변 시그널이 떴어요</strong>
          <span>{hitSignals.map((r) => r.name).join(', ')}</span>
        </p>
      )}

      {rows.length > 0 && (
        <PriceAlerts
          rows={alertRows}
          alerts={alerts}
          onChange={onAlertsChange}
          notifyPermission={notifyPermission}
          onEnableNotify={onEnableNotify}
        />
      )}

      <section className="panel pf-holdings">
        <div className="pf-head">
          <h2 className="pf-head-title">
            보유 종목
            {rows.length > 0 && <span className="pf-count mono">{rows.length}</span>}
          </h2>
          {!showForm && (
            <button type="button" className="pf-btn pf-btn-weak" onClick={() => setFormOpen(true)}>
              + 종목 추가
            </button>
          )}
        </div>

        {showForm && (
          <form ref={formRef} className="pf-form" onSubmit={handleSubmit}>
            <div className="pf-field">
              <label htmlFor="pf-symbol">종목코드</label>
              <input
                id="pf-symbol"
                list="pf-tickers"
                placeholder="005930"
                value={form.symbol}
                onChange={(e) => handleSymbolChange(e.target.value)}
              />
              <datalist id="pf-tickers">
                {tickers.map((t) => (
                  <option key={t.symbol} value={t.symbol}>
                    {t.name}
                  </option>
                ))}
              </datalist>
            </div>
            <div className="pf-field">
              <label htmlFor="pf-name">종목명</label>
              <input
                id="pf-name"
                placeholder="삼성전자"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              />
            </div>
            <div className="pf-field">
              <label htmlFor="pf-qty">수량</label>
              <input
                id="pf-qty"
                inputMode="decimal"
                placeholder="10"
                value={form.quantity}
                onChange={(e) => setForm((f) => ({ ...f, quantity: e.target.value }))}
              />
            </div>
            <div className="pf-field">
              <label htmlFor="pf-avg">평균 매입가</label>
              <input
                id="pf-avg"
                inputMode="decimal"
                placeholder="70,000"
                value={form.avgPrice}
                onChange={(e) => setForm((f) => ({ ...f, avgPrice: e.target.value }))}
              />
            </div>
            <div className="pf-field pf-field-wide">
              <label htmlFor="pf-memo">메모 (선택)</label>
              <input
                id="pf-memo"
                placeholder="장기 보유"
                value={form.memo ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, memo: e.target.value }))}
              />
            </div>
            <div className="pf-actions">
              <button type="submit" className="pf-btn pf-btn-primary">
                {editingId ? '수정 저장' : '추가'}
              </button>
              {holdings.length > 0 && (
                <button type="button" className="pf-btn" onClick={closeForm}>
                  취소
                </button>
              )}
            </div>
          </form>
        )}

        {error && <p className="pf-error">{error}</p>}
        {notice && <p className="pf-notice">{notice}</p>}

        {rows.length === 0 ? (
          <p className="pf-empty">
            보유 종목을 추가하면 최근 종가로 평가손익을 계산해 보여 드려요. 입력한 값은 이
            브라우저에만 저장되고 서버로 보내지 않아요.
          </p>
        ) : (
          <div className="pf-table-wrap">
            <table className="pf-table">
              <thead>
                <tr>
                  <th>종목</th>
                  <th className="num">수량</th>
                  <th className="num">평단</th>
                  <th className="num">현재가</th>
                  <th className="num">평가금액</th>
                  <th className="num">평가손익</th>
                  <th className="num">수익률</th>
                  <th className="num">비중</th>
                  <th>
                    <span className="sr-only">관리</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const dir = direction(r.pnl)
                  const signal = signalBySymbol.get(r.symbol)
                  return (
                    <tr key={r.id} className={editingId === r.id ? 'pf-row editing' : 'pf-row'}>
                      <td>
                        <div className="pf-stock">
                          <StockAvatar name={r.name} size="sm" />
                          <div className="pf-stock-text">
                            <span className="pf-name">{r.name}</span>
                            {signal && (
                              <span className={`pf-sig sev-${signal.severity}`}>
                                {signal.type === 'sentiment_surge_pos' ? '감정 급등' : '감정 급락'}
                              </span>
                            )}
                            <span className="pf-symbol mono">{r.symbol}</span>
                            {r.memo && <span className="pf-memo">{r.memo}</span>}
                          </div>
                        </div>
                      </td>
                      <td className="num mono">{r.quantity.toLocaleString('ko-KR')}</td>
                      <td className="num mono">{formatWon(r.avgPriceKrw)}</td>
                      <td className="num mono">
                        {r.close === null ? (
                          <span className="pf-noquote">시세 없음</span>
                        ) : (
                          <>
                            {formatWon(r.close)}
                            {r.changePct != null && (
                              <span className={`pf-chg mono dir-${direction(r.changePct)}`}>
                                {formatPct(r.changePct)}
                              </span>
                            )}
                            {r.priceSource === 'imported' && (
                              <span className="pf-imported">가져온 시세</span>
                            )}
                          </>
                        )}
                      </td>
                      <td className="num mono">{formatWon(r.value)}</td>
                      <td className={`num mono dir-${dir}`}>{formatSigned(r.pnl)}</td>
                      <td className={`num mono dir-${dir}`}>{formatPct(r.returnPct)}</td>
                      <td className="num mono">{formatPct(r.weight, 1, false)}</td>
                      <td className="num">
                        {/* td 자체를 flex 로 만들면 표 줄 높이·구분선이 어긋나서 안쪽 div 로 감싼다 */}
                        <div className="pf-rowbtns">
                          <button
                            type="button"
                            className="pf-btn pf-btn-sm"
                            onClick={() => handleEdit(r)}
                          >
                            수정
                          </button>
                          <button
                            type="button"
                            className="pf-btn pf-btn-sm pf-btn-danger"
                            onClick={() => handleDelete(r)}
                          >
                            삭제
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* 백업 버튼은 목록이 비어 있어도 보여야 한다 — 가져오기로 복구할 수 있어야 하므로. */}
        <div className="pf-foot">
          <span className="pf-foot-note mono">
            {rows.length > 0 &&
              (quotesStatus === 'loading'
                ? '시세 불러오는 중…'
                : quotesStatus === 'error'
                  ? '시세를 불러오지 못했어요 · 잠시 뒤 자동으로 다시 시도해요'
                  : `${quotesLive ? '실시간 (장중 · 네이버 금융 기준 · 15초마다 갱신)' : quoteDate ? `${quoteDate} 종가 기준` : '시세 기준일 없음'}${
                      totals.unpricedCount > 0
                        ? ` · 시세 없는 ${totals.unpricedCount}건은 평가 제외`
                        : ''
                    }`)}
          </span>
          <span className="pf-foot-btns">
            <button
              type="button"
              className="pf-btn pf-btn-sm"
              onClick={handleExport}
              disabled={holdings.length === 0}
            >
              내보내기
            </button>
            <button type="button" className="pf-btn pf-btn-sm" onClick={() => fileRef.current?.click()}>
              가져오기
            </button>
          </span>
        </div>
      </section>

      <input
        ref={fileRef}
        type="file"
        accept="application/json,.json"
        hidden
        onChange={handleImport}
      />
    </div>
  )
}
