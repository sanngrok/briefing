/**
 * market.ts — 국내 장중 시간대 판정 (순수 함수)
 *
 * 서버(api/live_quotes.py 의 is_market_live_window)와 같은 창을 본다:
 * 평일 09:00~18:00 KST (정규장 + 시간외 단일가).
 *
 * 프론트가 같은 판단을 따로 하는 이유는 요청을 보낼지 말지 정하기 위해서다.
 * 장 시간 밖에는 서버가 어차피 DB 종가를 그대로 돌려주므로 다시 불러도 값이
 * 바뀌지 않는데, 무료 인스턴스는 요청이 계속 오면 잠들지 않아 쿼터만 쓴다.
 *
 * 공휴일은 모른다(서버도 마찬가지). 휴장일에는 네이버가 직전 거래일 종가를
 * 주므로 값 자체는 맞고, 라벨만 "실시간(장중)"으로 뜬다.
 */

const KST = 'Asia/Seoul'
const OPEN_MINUTE = 9 * 60    // 09:00 정규장 시작
const CLOSE_MINUTE = 18 * 60  // 18:00 시간외 단일가 종료

const kstFormat = new Intl.DateTimeFormat('en-US', {
  timeZone: KST,
  weekday: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

/** 주어진 시각의 한국 기준 요일과 자정으로부터의 분(minute). */
export function kstMoment(now: Date = new Date()): { weekday: string; minute: number } {
  const parts: Record<string, string> = {}
  for (const p of kstFormat.formatToParts(now)) parts[p.type] = p.value
  return {
    weekday: parts.weekday ?? '',
    minute: Number(parts.hour) * 60 + Number(parts.minute),
  }
}

/** 지금이 국내 정규장~시간외 단일가 시간대인지(평일 09:00~18:00 KST). */
export function isMarketLiveWindow(now: Date = new Date()): boolean {
  const { weekday, minute } = kstMoment(now)
  if (weekday === 'Sat' || weekday === 'Sun') return false
  return minute >= OPEN_MINUTE && minute <= CLOSE_MINUTE
}
