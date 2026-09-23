/**
 * market.ts — 장 시간대 판정 (순수 함수)
 *
 * 프론트가 이 판단을 따로 하는 이유는 요청을 보낼지 말지 정하기 위해서다.
 * 장 시간 밖에는 서버가 어차피 같은 값을 돌려주는데, 무료 인스턴스는 요청이
 * 계속 오면 잠들지 않아 쿼터만 쓴다.
 *
 * - 국내: 평일 09:00~18:00 KST (정규장 + 시간외 단일가).
 *   서버(api/live_quotes.py 의 is_market_live_window)와 같은 창이다.
 * - 미국: 평일 09:30~16:00 America/New_York (정규장).
 *   한국 시간으로는 서머타임에 따라 22:30~05:00(겨울) / 21:30~04:00(여름)으로
 *   밀리는데, 표준시 이름으로 판정하면 브라우저의 표준시 데이터가 알아서 처리한다.
 *
 * 공휴일은 모른다(서버도 마찬가지). 휴장일엔 네이버가 직전 거래일 종가를 주므로
 * 값 자체는 맞고 라벨만 "실시간(장중)"으로 뜬다.
 */

const KST = 'Asia/Seoul'
const US_TZ = 'America/New_York'

const KR_OPEN_MINUTE = 9 * 60        // 09:00 정규장 시작
const KR_CLOSE_MINUTE = 18 * 60      // 18:00 시간외 단일가 종료
const US_OPEN_MINUTE = 9 * 60 + 30   // 09:30 ET
const US_CLOSE_MINUTE = 16 * 60      // 16:00 ET

const WEEKEND = ['Sat', 'Sun']

const formatters = new Map<string, Intl.DateTimeFormat>()

function formatterFor(timeZone: string): Intl.DateTimeFormat {
  let fmt = formatters.get(timeZone)
  if (!fmt) {
    fmt = new Intl.DateTimeFormat('en-US', {
      timeZone,
      weekday: 'short',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    })
    formatters.set(timeZone, fmt)
  }
  return fmt
}

/** 주어진 시각의 해당 표준시 기준 요일과 자정으로부터의 분(minute). */
export function momentIn(timeZone: string, now: Date = new Date()): {
  weekday: string
  minute: number
} {
  const parts: Record<string, string> = {}
  for (const p of formatterFor(timeZone).formatToParts(now)) parts[p.type] = p.value
  return {
    weekday: parts.weekday ?? '',
    minute: Number(parts.hour) * 60 + Number(parts.minute),
  }
}

function isWithin(timeZone: string, open: number, close: number, now: Date): boolean {
  const { weekday, minute } = momentIn(timeZone, now)
  if (WEEKEND.includes(weekday)) return false
  return minute >= open && minute <= close
}

/** 지금이 국내 정규장~시간외 단일가 시간대인지(평일 09:00~18:00 KST). */
export function isMarketLiveWindow(now: Date = new Date()): boolean {
  return isWithin(KST, KR_OPEN_MINUTE, KR_CLOSE_MINUTE, now)
}

/** 지금이 미국 정규장 시간대인지(평일 09:30~16:00 ET, 서머타임 자동 반영). */
export function isUsMarketWindow(now: Date = new Date()): boolean {
  return isWithin(US_TZ, US_OPEN_MINUTE, US_CLOSE_MINUTE, now)
}

/** 해외 종목인지 — 국내는 6자리 숫자 코드다. */
export function isWorldSymbol(symbol: string): boolean {
  return !/^\d{6}$/.test(symbol ?? '')
}
