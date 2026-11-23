// 목표가 · 손절가 알림 — 순수 계산 + 로컬 저장
//
// 보유 목록과 따로 저장한다. 토스 동기화 파일을 '가져오기' 하면 보유 목록은 통째로
// 바뀌는데, 그때 걸어 둔 목표가까지 날아가면 안 되기 때문이다. 키는 종목코드.
//
// 가격 단위는 종목이 거래되는 통화다 — 국내는 원, 해외는 달러. 해외 종목 목표가를
// 원화로 잡으면 주가가 그대로여도 환율만 움직여 알림이 울린다.
//
// 아침 메일(pipeline.py)도 같은 규칙으로 판정한다. 화면의 '메일 알림 설정 복사'가
// 만들어 주는 한 줄(toSecretLine)을 GitHub 시크릿 HOLDING_SYMBOLS 에 넣으면 된다.

import { isWorldSymbol } from './market'
import { normalizeSymbol, parseNumber } from './portfolio'

export const ALERTS_KEY = 'briefing.alerts.v1'
export const NOTIFIED_KEY = 'briefing.alerts.notified.v1'
/** 목표가·손절가에 이만큼(%) 다가오면 '근접'으로 알린다. pipeline.ALERT_NEAR_PCT 와 같아야 한다. */
export const NEAR_PCT = 3

export interface AlertSetting {
  target?: number
  stop?: number
}

/** 종목코드 → 설정 */
export type Alerts = Record<string, AlertSetting>

export type AlertCurrency = 'KRW' | 'USD'

export type AlertKind = 'target-hit' | 'stop-hit' | 'near-target' | 'near-stop' | 'watching'

export interface AlertStatus {
  kind: AlertKind
  /** 목표가까지 남은 상승률(%). 이미 넘었으면 0 이하. 목표가가 없으면 null */
  toTarget: number | null
  /** 손절가까지 남은 하락률(%). 이미 깨졌으면 0 이하. 손절가가 없으면 null */
  toStop: number | null
  /** 손절가(0) ~ 목표가(1) 사이에서 현재가 위치. 둘 다 있어야 한다. 0~1 로 자른다 */
  position: number | null
}

export function alertCurrency(symbol: string): AlertCurrency {
  return isWorldSymbol(symbol) ? 'USD' : 'KRW'
}

/**
 * 알림 판정에 쓸 현재가(종목 통화). 화면의 close 는 원화로 환산된 값이라 해외
 * 종목은 환율로 되돌린다. 환율이 없으면 판정하지 않는다(null).
 */
export function alertPrice(
  symbol: string,
  closeKrw: number | null,
  fxUsdKrw?: number | null,
): number | null {
  if (closeKrw == null || !Number.isFinite(closeKrw)) return null
  if (alertCurrency(symbol) === 'KRW') return closeKrw
  if (fxUsdKrw == null || !Number.isFinite(fxUsdKrw) || fxUsdKrw <= 0) return null
  return closeKrw / fxUsdKrw
}

export function hasAlert(s?: AlertSetting | null): s is AlertSetting {
  return !!s && (s.target != null || s.stop != null)
}

/** 도달 > 근접 > 감시 순으로 판정한다. 둘 다 근접이면 더 가까운 쪽. (순수) */
export function evaluateAlert(
  price: number,
  setting: AlertSetting,
  nearPct = NEAR_PCT,
): AlertStatus {
  const { target, stop } = setting
  const toTarget = target != null ? ((target - price) / price) * 100 : null
  const toStop = stop != null ? ((price - stop) / price) * 100 : null
  const position =
    target != null && stop != null && target > stop
      ? Math.min(1, Math.max(0, (price - stop) / (target - stop)))
      : null

  let kind: AlertKind = 'watching'
  if (target != null && price >= target) kind = 'target-hit'
  else if (stop != null && price <= stop) kind = 'stop-hit'
  else {
    const nearT = toTarget != null && toTarget <= nearPct
    const nearS = toStop != null && toStop <= nearPct
    if (nearT && nearS) kind = (toTarget as number) <= (toStop as number) ? 'near-target' : 'near-stop'
    else if (nearT) kind = 'near-target'
    else if (nearS) kind = 'near-stop'
  }
  return { kind, toTarget, toStop, position }
}

export function isHit(kind: AlertKind): boolean {
  return kind === 'target-hit' || kind === 'stop-hit'
}

/**
 * 입력칸 두 개를 검증한다. 둘 다 비우면 설정 해제(setting=null).
 * 현재가를 주면 '이미 도달한 값'인지 알려 주지는 않는다 — 일부러 그렇게 걸 수도 있다.
 */
export function validateAlertInput(
  targetRaw: string,
  stopRaw: string,
): { ok: true; setting: AlertSetting | null } | { ok: false; error: string } {
  const target = parseNumber(targetRaw)
  const stop = parseNumber(stopRaw)
  if (targetRaw.trim() && target === null) return { ok: false, error: '목표가를 숫자로 입력하세요.' }
  if (stopRaw.trim() && stop === null) return { ok: false, error: '손절가를 숫자로 입력하세요.' }
  if (target !== null && target <= 0) return { ok: false, error: '목표가는 0보다 커야 해요.' }
  if (stop !== null && stop <= 0) return { ok: false, error: '손절가는 0보다 커야 해요.' }
  if (target !== null && stop !== null && target <= stop) {
    return { ok: false, error: '목표가는 손절가보다 높아야 해요.' }
  }
  if (target === null && stop === null) return { ok: true, setting: null }
  return {
    ok: true,
    setting: { ...(target !== null ? { target } : {}), ...(stop !== null ? { stop } : {}) },
  }
}

/** 설정을 바꾼 새 객체. setting 이 null 이면 그 종목을 지운다. (순수) */
export function setAlert(alerts: Alerts, symbol: string, setting: AlertSetting | null): Alerts {
  const key = normalizeSymbol(symbol)
  const next = { ...alerts }
  if (setting && hasAlert(setting)) next[key] = setting
  else delete next[key]
  return next
}

/** 저장본·파일에서 읽는다. 깨진 값은 버린다. */
export function parseAlerts(raw: unknown): Alerts {
  const src =
    raw && typeof raw === 'object' && !Array.isArray(raw)
      ? ((raw as { alerts?: unknown }).alerts ?? raw)
      : null
  if (!src || typeof src !== 'object' || Array.isArray(src)) return {}
  const out: Alerts = {}
  for (const [sym, v] of Object.entries(src as Record<string, unknown>)) {
    if (!v || typeof v !== 'object') continue
    const o = v as Record<string, unknown>
    const target = Number(o.target)
    const stop = Number(o.stop)
    const setting: AlertSetting = {
      ...(Number.isFinite(target) && target > 0 ? { target } : {}),
      ...(Number.isFinite(stop) && stop > 0 ? { stop } : {}),
    }
    if (setting.target != null && setting.stop != null && setting.target <= setting.stop) continue
    const key = normalizeSymbol(sym)
    if (key && hasAlert(setting)) out[key] = setting
  }
  return out
}

function plain(n: number): string {
  // 시크릿 한 줄에는 콤마 없이. 달러는 센트까지만.
  return String(Math.round(n * 100) / 100)
}

/**
 * GitHub 시크릿 HOLDING_SYMBOLS 에 넣을 한 줄.
 *   '005930:stop=170000:target=250000,TSLA,PLTR:target=200'
 * 보유 종목 순서를 따르고, 보유하지 않은 종목의 설정은 넣지 않는다. (순수)
 */
export function toSecretLine(symbols: string[], alerts: Alerts): string {
  const seen = new Set<string>()
  const parts: string[] = []
  for (const raw of symbols) {
    const sym = normalizeSymbol(raw)
    if (!sym || seen.has(sym)) continue
    seen.add(sym)
    const a = alerts[sym]
    let part = sym
    if (a?.stop != null) part += `:stop=${plain(a.stop)}`
    if (a?.target != null) part += `:target=${plain(a.target)}`
    parts.push(part)
  }
  return parts.join(',')
}

/** '251,000원' / '$201.35' */
export function formatAlertPrice(n: number | null | undefined, currency: AlertCurrency): string {
  if (n == null || !Number.isFinite(n)) return '—'
  if (currency === 'USD') {
    return `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  }
  return `${Math.round(n).toLocaleString('ko-KR')}원`
}

export function loadAlerts(): Alerts {
  try {
    const raw = window.localStorage.getItem(ALERTS_KEY)
    return raw ? parseAlerts(JSON.parse(raw)) : {}
  } catch {
    return {}
  }
}

export function saveAlerts(alerts: Alerts): boolean {
  try {
    window.localStorage.setItem(ALERTS_KEY, JSON.stringify(alerts))
    return true
  } catch {
    return false
  }
}

/**
 * 브라우저 알림을 이미 띄운 것들 — 하루에 같은 종목·같은 종류로 한 번만 띄운다.
 * 오늘 것만 남기고 버린다. (순수)
 */
export function notifyKey(date: string, symbol: string, kind: AlertKind): string {
  return `${date}:${symbol}:${kind}`
}

export function pruneNotified(keys: string[], today: string): string[] {
  return keys.filter((k) => k.startsWith(`${today}:`))
}

/** 화면·배지·브라우저 알림이 함께 쓰는 한 줄. */
export interface AlertRow {
  symbol: string
  name: string
  currency: AlertCurrency
  /** 판정에 쓴 현재가(종목 통화). 시세·환율이 없으면 null */
  price: number | null
  /** 현재가가 가져온 스냅샷 값인지(실시간·종가가 아님) */
  stale: boolean
  setting: AlertSetting | null
  /** 설정이 없거나 현재가가 없으면 null */
  status: AlertStatus | null
}

const URGENCY: Record<AlertKind, number> = {
  'target-hit': 0,
  'stop-hit': 0,
  'near-target': 1,
  'near-stop': 1,
  watching: 2,
}

/**
 * 보유 종목 줄에 알림 설정과 판정을 붙인다. 급한 것(도달 → 근접 → 감시 → 미설정)
 * 순으로, 같은 급이면 원래 순서. (순수)
 */
export function buildAlertRows(
  rows: {
    symbol: string
    name: string
    close: number | null
    priceSource?: string | null
    /** 가져오기 시점 환율 — 현재 환율을 못 받았을 때 폴백(평가 계산과 같은 규칙) */
    fxAtImport?: number | null
  }[],
  alerts: Alerts,
  fxUsdKrw?: number | null,
): AlertRow[] {
  const out = rows.map((r, i) => {
    const setting = alerts[normalizeSymbol(r.symbol)] ?? null
    const price = alertPrice(r.symbol, r.close, fxUsdKrw ?? r.fxAtImport)
    const status = setting && hasAlert(setting) && price !== null ? evaluateAlert(price, setting) : null
    const row: AlertRow = {
      symbol: r.symbol,
      name: r.name,
      currency: alertCurrency(r.symbol),
      price,
      stale: r.priceSource === 'imported',
      setting: setting && hasAlert(setting) ? setting : null,
      status,
    }
    return { row, i }
  })
  const rank = (r: AlertRow) => (r.status ? URGENCY[r.status.kind] : r.setting ? 2.5 : 3)
  return out.sort((a, b) => rank(a.row) - rank(b.row) || a.i - b.i).map((x) => x.row)
}
