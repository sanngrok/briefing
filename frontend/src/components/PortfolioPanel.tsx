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

const EMPTY_FORM: HoldingInput = { symbol: '', name: '', quantity: '', avgPrice: '', memo: '' }

interface Props {
  holdings: Holding[]
  onChange: (next: Holding[]) => void
  quotes: Quote[]
  quoteDate?: string | null
  tickers: Ticker[]
  signals: Signal[]
  storageFailed?: boolean
}

export function PortfolioPanel({
  holdings,
  onChange,
  quotes,
  quoteDate,
  tickers,
  signals,
  storageFailed,
}: Props) {
  const [form, setForm] = useState<HoldingInput>(EMPTY_FORM)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const rows = useMemo(() => sortByReturn(computeRows(holdings, quotes)), [holdings, quotes])
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
      const merged = mergeHolding(duplicate, holding)
      onChange(holdings.map((h) => (h.id === duplicate.id ? merged : h)))
      flash(`${merged.name} 추가 매수로 합산 (평단 ${formatWon(merged.avgPrice)}원)`)
    } else {
      onChange([...holdings, holding])
      flash(`${holding.name} 추가됨`)
    }
    resetForm()
  }

  function handleEdit(row: HoldingRow) {
    setEditingId(row.id)
    setError('')
    setForm({
      symbol: row.symbol,
      name: row.name,
      quantity: String(row.quantity),
      avgPrice: String(row.avgPrice),
      memo: row.memo ?? '',
    })
  }

  function handleDelete(row: HoldingRow) {
    if (!window.confirm(`${row.name}(${row.symbol})을(를) 삭제할까요?`)) return
    onChange(holdings.filter((h) => h.id !== row.id))
    if (editingId === row.id) resetForm()
    flash(`${row.name} 삭제됨`)
  }

  function handleExport() {
    const blob = new Blob([serializeHoldings(holdings)], { type: 'application/json' })
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
      const parsed = parseHoldings(JSON.parse(await file.text()))
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
      resetForm()
      flash(`${parsed.length}건 불러옴`)
    } catch {
      setError('JSON 파일을 읽지 못했습니다.')
    }
  }

  const totalDir = direction(totals.pnl)
  const dayDir = direction(totals.dayPnl)

  return (
    <div className="panel pf">
      {storageFailed && (
        <p className="pf-warn">
          브라우저 저장소를 쓸 수 없어 새로고침하면 사라집니다. (사생활 보호 모드 등)
        </p>
      )}

      <form className="pf-form" onSubmit={handleSubmit}>
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
          {editingId && (
            <button type="button" className="pf-btn" onClick={resetForm}>
              취소
            </button>
          )}
        </div>
      </form>

      {error && <p className="pf-error">{error}</p>}
      {notice && <p className="pf-notice">{notice}</p>}

      {rows.length === 0 ? (
        <p className="empty">
          보유 종목을 추가하면 최근 종가로 평가손익을 계산해 보여줍니다. 입력값은 이 브라우저에만
          저장되며 서버로 전송되지 않습니다.
        </p>
      ) : (
        <>
          <div className="pf-totals">
            <div className="pf-total">
              <span className="pf-total-label">매입금액</span>
              <span className="pf-total-value mono">{formatWon(totals.cost)}</span>
            </div>
            <div className="pf-total">
              <span className="pf-total-label">평가금액</span>
              <span className="pf-total-value mono">{formatWon(totals.value)}</span>
            </div>
            <div className="pf-total">
              <span className="pf-total-label">평가손익</span>
              <span className={`pf-total-value mono dir-${totalDir}`}>
                {formatSigned(totals.pnl)}
              </span>
            </div>
            <div className="pf-total">
              <span className="pf-total-label">수익률</span>
              <span className={`pf-total-value mono dir-${totalDir}`}>
                {formatPct(totals.returnPct)}
              </span>
            </div>
            <div className="pf-total">
              <span className="pf-total-label">전일 대비</span>
              <span className={`pf-total-value mono dir-${dayDir}`}>
                {formatSigned(totals.dayPnl)}
              </span>
            </div>
          </div>

          {hitSignals.length > 0 && (
            <p className="pf-signal-note">
              보유 종목 중 {hitSignals.length}건에 감정 급변 시그널이 있습니다 —{' '}
              {hitSignals.map((r) => r.name).join(', ')}
            </p>
          )}

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
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const dir = direction(r.pnl)
                  const signal = signalBySymbol.get(r.symbol)
                  return (
                    <tr key={r.id} className={editingId === r.id ? 'pf-row editing' : 'pf-row'}>
                      <td>
                        <span className="pf-name">{r.name}</span>
                        {signal && (
                          <span className={`pf-sig sev-${signal.severity}`}>
                            {signal.type === 'sentiment_surge_pos' ? '감정 급등' : '감정 급락'}
                          </span>
                        )}
                        <span className="pf-symbol mono">{r.symbol}</span>
                        {r.memo && <span className="pf-memo">{r.memo}</span>}
                      </td>
                      <td className="num mono">{r.quantity.toLocaleString('ko-KR')}</td>
                      <td className="num mono">{formatWon(r.avgPrice)}</td>
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
                          </>
                        )}
                      </td>
                      <td className="num mono">{formatWon(r.value)}</td>
                      <td className={`num mono dir-${dir}`}>{formatSigned(r.pnl)}</td>
                      <td className={`num mono dir-${dir}`}>{formatPct(r.returnPct)}</td>
                      <td className="num mono">{formatPct(r.weight, 1, false)}</td>
                      <td className="num pf-rowbtns">
                        <button type="button" className="pf-btn pf-btn-sm" onClick={() => handleEdit(r)}>
                          수정
                        </button>
                        <button
                          type="button"
                          className="pf-btn pf-btn-sm pf-btn-danger"
                          onClick={() => handleDelete(r)}
                        >
                          삭제
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* 백업 버튼은 목록이 비어 있어도 보여야 한다 — 가져오기로 복구할 수 있어야 하므로. */}
      <div className="pf-foot">
        <span className="pf-foot-note mono">
          {rows.length > 0 &&
            `${quoteDate ? `${quoteDate} 종가 기준` : '시세 기준일 없음'}${
              totals.unpricedCount > 0 ? ` · 시세 없는 ${totals.unpricedCount}건은 평가 제외` : ''
            }`}
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
