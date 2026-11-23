// 내 자산 추이 — 하루 한 점(총 평가금액·매입금액)을 브라우저에 쌓는다.
//
// 보유 종목과 마찬가지로 서버에 올리지 않는다(개인 자산 규모라서). 점은 두 곳에서 온다.
//   1) 화면: 사이트를 열어 시세가 붙으면 그날 값을 기록하고, 다시 열면 덮어쓴다.
//   2) toss_sync.py: 평일 16:30 마다 portfolio.json 의 history 에 그날 값을 쌓는다.
//      '가져오기' 하면 여기 기록과 합친다 — 사이트를 안 연 날도 점이 생긴다.
// 같은 날짜가 겹치면 더 나중에 기록된 값(at)을 쓴다.

export const HISTORY_KEY = 'briefing.portfolio.history.v1'
/** 하루 한 점이라 2년 남짓. 오래된 점부터 버린다. */
export const HISTORY_MAX = 800

export interface Snapshot {
  /** KST 날짜 'YYYY-MM-DD' */
  date: string
  /** 총 평가금액(원) */
  value: number
  /** 그 평가에 쓰인 매입금액(원) — 입금·추가매수로 오른 건지 수익으로 오른 건지 가른다 */
  cost: number
  /** 기록 시각(ISO). 같은 날짜가 겹치면 더 늦은 쪽이 이긴다. */
  at?: string
}

export type HistoryRange = '1W' | '1M' | '3M' | 'ALL'

const RANGE_DAYS: Record<Exclude<HistoryRange, 'ALL'>, number> = { '1W': 7, '1M': 30, '3M': 91 }

/** 지금 시각의 KST 날짜. 브라우저 시간대와 상관없이 한국 날짜로 센다. */
export function kstDate(now = new Date()): string {
  return new Date(now.getTime() + 9 * 3600_000).toISOString().slice(0, 10)
}

function isDate(s: unknown): s is string {
  return typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s)
}

/** 저장본·파일에서 읽은 값을 검증한다. 깨진 점은 버리고 날짜순으로 정렬. */
export function parseHistory(raw: unknown): Snapshot[] {
  const list = Array.isArray(raw)
    ? raw
    : Array.isArray((raw as { history?: unknown })?.history)
      ? (raw as { history: unknown[] }).history
      : []
  const out: Snapshot[] = []
  for (const item of list) {
    if (!item || typeof item !== 'object') continue
    const o = item as Record<string, unknown>
    const value = Number(o.value)
    const cost = Number(o.cost)
    if (!isDate(o.date) || !Number.isFinite(value) || value < 0) continue
    if (!Number.isFinite(cost) || cost < 0) continue
    out.push({
      date: o.date,
      value,
      cost,
      ...(typeof o.at === 'string' ? { at: o.at } : {}),
    })
  }
  return mergeHistory([], out)
}

function newer(a: Snapshot, b: Snapshot): Snapshot {
  // at 이 없는 쪽(옛 저장본)은 지는 쪽으로 친다
  return (b.at ?? '') >= (a.at ?? '') ? b : a
}

/** 두 기록을 날짜별로 합친다. 같은 날짜는 더 나중에 기록된 값. (순수) */
export function mergeHistory(base: Snapshot[], incoming: Snapshot[]): Snapshot[] {
  const byDate = new Map<string, Snapshot>()
  for (const s of base) byDate.set(s.date, s)
  for (const s of incoming) {
    const prev = byDate.get(s.date)
    byDate.set(s.date, prev ? newer(prev, s) : s)
  }
  const sorted = [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date))
  return sorted.slice(-HISTORY_MAX)
}

/**
 * 오늘 점을 넣거나 덮어쓴다. 값이 그대로면 같은 배열을 돌려줘 저장을 건너뛸 수
 * 있게 한다(장중 15초 폴링마다 저장소를 쓰지 않도록). (순수)
 */
export function recordSnapshot(history: Snapshot[], snap: Snapshot): Snapshot[] {
  const last = history[history.length - 1]
  if (
    last &&
    last.date === snap.date &&
    Math.round(last.value) === Math.round(snap.value) &&
    Math.round(last.cost) === Math.round(snap.cost)
  ) {
    return history
  }
  return mergeHistory(history, [snap])
}

/** 기간으로 자른다. 기준은 오늘(KST)부터 거꾸로 센 달력 날짜. (순수) */
export function sliceRange(history: Snapshot[], range: HistoryRange, today: string): Snapshot[] {
  if (range === 'ALL') return history
  const t = new Date(`${today}T00:00:00Z`)
  t.setUTCDate(t.getUTCDate() - (RANGE_DAYS[range] - 1))
  const from = t.toISOString().slice(0, 10)
  return history.filter((s) => s.date >= from)
}

export interface HistorySummary {
  first: Snapshot
  last: Snapshot
  /** 평가금액 변화 */
  change: number
  changePct: number | null
  /** 그 사이 매입금액 변화(추가 매수·매도) */
  costChange: number
  /** 매입금액 변화를 뺀 순수 평가 변동 = 수익으로 늘어난 몫 */
  gain: number
}

/** 기간 처음과 끝을 비교한다. 점이 2개 미만이면 null. (순수) */
export function summarize(points: Snapshot[]): HistorySummary | null {
  if (points.length < 2) return null
  const first = points[0]
  const last = points[points.length - 1]
  const change = last.value - first.value
  const costChange = last.cost - first.cost
  return {
    first,
    last,
    change,
    changePct: first.value > 0 ? (change / first.value) * 100 : null,
    costChange,
    gain: change - costChange,
  }
}

export function loadHistory(): Snapshot[] {
  try {
    const raw = window.localStorage.getItem(HISTORY_KEY)
    return raw ? parseHistory(JSON.parse(raw)) : []
  } catch {
    return []
  }
}

export function saveHistory(history: Snapshot[]): boolean {
  try {
    window.localStorage.setItem(HISTORY_KEY, JSON.stringify(history))
    return true
  } catch {
    return false
  }
}
