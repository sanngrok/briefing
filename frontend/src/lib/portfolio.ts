// 내 포트폴리오 — 순수 계산 + 로컬 저장 (레이어 C 전용)
//
// 개인 매매 정보이므로 서버에 올리지 않고 브라우저 localStorage 에만 둔다.
// 덕분에 서빙 API 는 계속 읽기 전용(하드룰 §4)으로 유지된다.
// 계산은 전부 순수 함수로 떼어내 단위 테스트(portfolio.test.ts)로 고정한다.

export const STORAGE_KEY = 'briefing.portfolio.v1'
export const EXPORT_VERSION = 1

/** 사용자가 입력한 보유 1건. */
export interface Holding {
  id: string
  symbol: string
  name: string
  quantity: number
  avgPrice: number
  memo?: string
}

/** 폼 입력값(문자열 그대로). 검증을 거쳐 Holding 이 된다. */
export interface HoldingInput {
  symbol: string
  name: string
  quantity: string
  avgPrice: string
  memo?: string
}

/** 시세를 붙여 평가까지 끝낸 한 줄. 시세가 없으면 평가값은 null. */
export interface HoldingRow extends Holding {
  close: number | null
  changePct: number | null
  cost: number
  value: number | null
  pnl: number | null
  returnPct: number | null
  dayPnl: number | null
  weight: number | null
}

export interface PortfolioTotals {
  /** 전체 매입금액 (시세 없는 종목 포함) */
  cost: number
  /** 시세가 있어 평가 가능한 종목의 매입금액 — 수익률의 분모 */
  pricedCost: number
  value: number
  pnl: number
  returnPct: number | null
  /** 전일 종가 대비 평가손익 */
  dayPnl: number
  count: number
  /** 시세를 못 붙인 종목 수 */
  unpricedCount: number
}

/** 시세 조회용 최소 형태 (api/client.ts 의 Quote 와 호환). */
export interface QuoteLike {
  symbol: string
  close?: number | null
  change_pct?: number | null
}

// --------------------------------------------------------------------
// 검증 / 정규화
// --------------------------------------------------------------------

/** 국내 종목코드 표기를 통일한다. 숫자 6자리(앞자리 0 보존)가 기본. */
export function normalizeSymbol(raw: string): string {
  const trimmed = (raw ?? '').trim().toUpperCase().replace(/\s+/g, '')
  if (/^\d{1,6}$/.test(trimmed)) return trimmed.padStart(6, '0')
  return trimmed
}

/** '1,234.5' 처럼 콤마가 섞인 입력도 받아준다. 숫자가 아니면 null. */
export function parseNumber(raw: string): number | null {
  const cleaned = (raw ?? '').trim().replace(/,/g, '')
  if (cleaned === '') return null
  const n = Number(cleaned)
  return Number.isFinite(n) ? n : null
}

/**
 * 폼 입력을 검증해 Holding 으로 만든다.
 * 실패하면 사용자에게 그대로 보여줄 한국어 메시지를 돌려준다.
 */
export function validateHolding(
  input: HoldingInput,
  id: string,
): { ok: true; holding: Holding } | { ok: false; error: string } {
  const symbol = normalizeSymbol(input.symbol)
  if (!symbol) return { ok: false, error: '종목코드를 입력하세요.' }
  if (symbol.length > 12) return { ok: false, error: '종목코드가 너무 깁니다.' }

  const quantity = parseNumber(input.quantity)
  if (quantity === null) return { ok: false, error: '수량을 숫자로 입력하세요.' }
  if (quantity <= 0) return { ok: false, error: '수량은 0보다 커야 합니다.' }

  const avgPrice = parseNumber(input.avgPrice)
  if (avgPrice === null) return { ok: false, error: '평균 매입가를 숫자로 입력하세요.' }
  if (avgPrice < 0) return { ok: false, error: '평균 매입가는 0 이상이어야 합니다.' }

  const name = (input.name ?? '').trim() || symbol
  const memo = (input.memo ?? '').trim()

  return {
    ok: true,
    holding: { id, symbol, name, quantity, avgPrice, ...(memo ? { memo } : {}) },
  }
}

/** 같은 종목을 두 번 담지 않도록 — 수정 중인 자기 자신(exceptId)은 제외하고 본다. */
export function findDuplicate(
  holdings: Holding[],
  symbol: string,
  exceptId?: string,
): Holding | undefined {
  const s = normalizeSymbol(symbol)
  return holdings.find((h) => h.symbol === s && h.id !== exceptId)
}

/** 같은 종목을 추가할 때 수량가중으로 평단가를 합친다(물타기). */
export function mergeHolding(base: Holding, added: Holding): Holding {
  const quantity = base.quantity + added.quantity
  const avgPrice =
    quantity > 0
      ? (base.quantity * base.avgPrice + added.quantity * added.avgPrice) / quantity
      : base.avgPrice
  return { ...base, name: added.name || base.name, quantity, avgPrice }
}

// --------------------------------------------------------------------
// 평가 계산 (순수)
// --------------------------------------------------------------------

/** 등락률로 전일 종가를 역산한다. -100% 이하는 역산 불가라 null. */
export function previousClose(close: number, changePct: number | null | undefined): number | null {
  if (changePct == null) return null
  const ratio = 1 + changePct / 100
  if (ratio <= 0) return null
  return close / ratio
}

/** 보유 목록에 시세를 붙여 평가 결과를 만든다. 시세가 없으면 평가값은 null. */
export function computeRows(holdings: Holding[], quotes: QuoteLike[]): HoldingRow[] {
  const bySymbol = new Map<string, QuoteLike>()
  for (const q of quotes ?? []) bySymbol.set(normalizeSymbol(q.symbol), q)

  const rows: HoldingRow[] = (holdings ?? []).map((h) => {
    const quote = bySymbol.get(h.symbol)
    const close = quote?.close ?? null
    const changePct = quote?.change_pct ?? null
    const cost = h.quantity * h.avgPrice
    const value = close === null ? null : h.quantity * close
    const pnl = value === null ? null : value - cost
    const returnPct = pnl === null || cost <= 0 ? null : (pnl / cost) * 100
    const prev = close === null ? null : previousClose(close, changePct)
    const dayPnl = close === null || prev === null ? null : (close - prev) * h.quantity
    return { ...h, close, changePct, cost, value, pnl, returnPct, dayPnl, weight: null }
  })

  // 비중은 평가금액 합계 대비 — 합계가 나온 뒤에야 계산할 수 있다.
  const totalValue = rows.reduce((sum, r) => sum + (r.value ?? 0), 0)
  if (totalValue > 0) {
    for (const r of rows) r.weight = r.value === null ? null : (r.value / totalValue) * 100
  }
  return rows
}

/** 평가 결과 합계. 수익률은 '시세가 있는 종목'만으로 계산해 분모를 맞춘다. */
export function computeTotals(rows: HoldingRow[]): PortfolioTotals {
  let cost = 0
  let pricedCost = 0
  let value = 0
  let dayPnl = 0
  let unpricedCount = 0

  for (const r of rows ?? []) {
    cost += r.cost
    if (r.value === null) {
      unpricedCount += 1
      continue
    }
    pricedCost += r.cost
    value += r.value
    dayPnl += r.dayPnl ?? 0
  }

  const pnl = value - pricedCost
  return {
    cost,
    pricedCost,
    value,
    pnl,
    returnPct: pricedCost > 0 ? (pnl / pricedCost) * 100 : null,
    dayPnl,
    count: (rows ?? []).length,
    unpricedCount,
  }
}

/** 수익률 내림차순 정렬 — 평가 불가(null)는 항상 뒤로. */
export function sortByReturn(rows: HoldingRow[]): HoldingRow[] {
  return [...(rows ?? [])].sort((a, b) => {
    if (a.returnPct === null && b.returnPct === null) return 0
    if (a.returnPct === null) return 1
    if (b.returnPct === null) return -1
    return b.returnPct - a.returnPct
  })
}

// --------------------------------------------------------------------
// 저장 / 내보내기
// --------------------------------------------------------------------

/** 저장본(JSON)에서 Holding 목록을 복원한다. 깨진 항목은 버린다. */
export function parseHoldings(raw: unknown): Holding[] {
  const list = Array.isArray(raw)
    ? raw
    : Array.isArray((raw as { holdings?: unknown })?.holdings)
      ? (raw as { holdings: unknown[] }).holdings
      : null
  if (!list) return []

  const out: Holding[] = []
  const seen = new Set<string>()
  for (const item of list) {
    if (!item || typeof item !== 'object') continue
    const o = item as Record<string, unknown>
    const symbol = normalizeSymbol(String(o.symbol ?? ''))
    const quantity = Number(o.quantity)
    const avgPrice = Number(o.avgPrice)
    if (!symbol || !Number.isFinite(quantity) || quantity <= 0) continue
    if (!Number.isFinite(avgPrice) || avgPrice < 0) continue
    if (seen.has(symbol)) continue          // 같은 종목 중복 저장본 방어
    seen.add(symbol)
    const memo = typeof o.memo === 'string' ? o.memo.trim() : ''
    out.push({
      id: typeof o.id === 'string' && o.id ? o.id : `${symbol}-${out.length}`,
      symbol,
      name: typeof o.name === 'string' && o.name.trim() ? o.name.trim() : symbol,
      quantity,
      avgPrice,
      ...(memo ? { memo } : {}),
    })
  }
  return out
}

/** 백업용 JSON 문자열. */
export function serializeHoldings(holdings: Holding[], now = new Date()): string {
  return JSON.stringify(
    { version: EXPORT_VERSION, exportedAt: now.toISOString(), holdings },
    null,
    2,
  )
}

export function loadHoldings(): Holding[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    return raw ? parseHoldings(JSON.parse(raw)) : []
  } catch {
    return []   // 사생활 보호 모드·손상된 저장본 등에서 앱이 죽지 않도록
  }
}

export function saveHoldings(holdings: Holding[]): boolean {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: EXPORT_VERSION, holdings }))
    return true
  } catch {
    return false
  }
}

export function newId(): string {
  const c = globalThis.crypto
  if (c && typeof c.randomUUID === 'function') return c.randomUUID()
  return `h-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

// --------------------------------------------------------------------
// 표시 포맷
// --------------------------------------------------------------------

/** 원화 금액. 소수점 매입가가 섞여도 표시는 정수로 반올림한다. */
export function formatWon(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—'
  return Math.round(n).toLocaleString('ko-KR')
}

/** 부호를 앞에 붙인 금액 (손익 표시용). */
export function formatSigned(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—'
  const rounded = Math.round(n)
  return `${rounded > 0 ? '+' : rounded < 0 ? '−' : ''}${Math.abs(rounded).toLocaleString('ko-KR')}`
}

/** 등락률·수익률. signed=false 면 비중처럼 부호가 의미 없는 값에 쓴다. */
export function formatPct(n: number | null | undefined, digits = 2, signed = true): string {
  if (n == null || !Number.isFinite(n)) return '—'
  if (!signed) return `${n.toFixed(digits)}%`
  return `${n > 0 ? '+' : n < 0 ? '−' : ''}${Math.abs(n).toFixed(digits)}%`
}

/** 국내 관행: 상승 빨강 / 하락 파랑 (index.css 의 dir-* 와 짝) */
export function direction(n: number | null | undefined): 'up' | 'down' | 'flat' {
  if (n == null || !Number.isFinite(n) || n === 0) return 'flat'
  return n > 0 ? 'up' : 'down'
}
