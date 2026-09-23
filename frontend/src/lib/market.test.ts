import { describe, expect, it } from 'vitest'
import { isMarketLiveWindow, kstMoment } from './market'

/** KST 시각을 UTC 기준 Date 로. (KST = UTC+9, 서머타임 없음) */
function kst(iso: string): Date {
  return new Date(`${iso}+09:00`)
}

describe('isMarketLiveWindow', () => {
  it('평일 장중이면 true', () => {
    // 2026-09-22 는 화요일
    expect(isMarketLiveWindow(kst('2026-09-22T11:00:00'))).toBe(true)
  })

  it('시간외 단일가 시간대도 true', () => {
    expect(isMarketLiveWindow(kst('2026-09-22T17:30:00'))).toBe(true)
  })

  it('개장 전이면 false', () => {
    expect(isMarketLiveWindow(kst('2026-09-22T08:59:00'))).toBe(false)
  })

  it('시간외까지 끝나면 false', () => {
    expect(isMarketLiveWindow(kst('2026-09-22T18:01:00'))).toBe(false)
  })

  it('경계(09:00, 18:00)는 포함', () => {
    expect(isMarketLiveWindow(kst('2026-09-22T09:00:00'))).toBe(true)
    expect(isMarketLiveWindow(kst('2026-09-22T18:00:00'))).toBe(true)
  })

  it('주말은 장중 시간대여도 false', () => {
    // 2026-09-26 토요일 / 2026-09-27 일요일
    expect(isMarketLiveWindow(kst('2026-09-26T11:00:00'))).toBe(false)
    expect(isMarketLiveWindow(kst('2026-09-27T11:00:00'))).toBe(false)
  })

  it('자정 직후도 0 분으로 읽어 false (h23 경계)', () => {
    expect(isMarketLiveWindow(kst('2026-09-22T00:00:00'))).toBe(false)
    expect(kstMoment(kst('2026-09-22T00:00:00')).minute).toBe(0)
  })

  it('브라우저 표준시와 무관하게 KST 로 판정한다', () => {
    // 2026-09-22T02:00Z = KST 11:00 (장중) — 실행 환경 타임존과 무관해야 한다
    expect(isMarketLiveWindow(new Date('2026-09-22T02:00:00Z'))).toBe(true)
    // 2026-09-22T23:00Z = KST 다음날 08:00 (개장 전)
    expect(isMarketLiveWindow(new Date('2026-09-22T23:00:00Z'))).toBe(false)
  })
})

describe('kstMoment', () => {
  it('요일과 분을 KST 로 돌려준다', () => {
    expect(kstMoment(kst('2026-09-22T09:30:00'))).toEqual({
      weekday: 'Tue',
      minute: 9 * 60 + 30,
    })
  })
})
