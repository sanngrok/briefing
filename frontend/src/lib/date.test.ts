import { describe, expect, it } from 'vitest'
import { formatKoDate } from './date'

describe('formatKoDate', () => {
  it('월·일·요일로 읽기 쉽게', () => {
    expect(formatKoDate('2026-11-20')).toBe('11월 20일 (금)')
    expect(formatKoDate('2026-11-23')).toBe('11월 23일 (월)')
    expect(formatKoDate('2026-01-04')).toBe('1월 4일 (일)')
  })

  it('비었으면 빈 문자열, 모르는 형식은 그대로', () => {
    expect(formatKoDate(undefined)).toBe('')
    expect(formatKoDate(null)).toBe('')
    expect(formatKoDate('어제')).toBe('어제')
  })
})
