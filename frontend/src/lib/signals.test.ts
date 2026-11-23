import { describe, expect, it } from 'vitest'
import type { Signal } from '../api/client'
import { signalsOfDay } from './signals'

function sig(date: string, symbol: string): Signal {
  return { date, symbol, type: 'sentiment_surge_pos', severity: 'low', evidence: {} }
}

// API 는 날짜 내림차순으로 준다
const ALL = [sig('2026-11-20', 'A'), sig('2026-11-19', 'B'), sig('2026-11-19', 'C'), sig('2026-11-18', 'D')]

describe('signalsOfDay', () => {
  it('리포트 날짜 하루치만 고른다', () => {
    expect(signalsOfDay(ALL, '2026-11-19').map((s) => s.symbol)).toEqual(['B', 'C'])
  })

  it('리포트 날짜에 시그널이 없으면 빈 목록 — 지난 시그널로 채우지 않는다', () => {
    expect(signalsOfDay(ALL, '2026-11-21')).toEqual([])
  })

  it('리포트를 못 받았으면 가장 최근 시그널 날짜로', () => {
    expect(signalsOfDay(ALL, null).map((s) => s.symbol)).toEqual(['A'])
    expect(signalsOfDay([...ALL].reverse(), undefined).map((s) => s.symbol)).toEqual(['A'])
  })

  it('시그널이 하나도 없으면 빈 목록', () => {
    expect(signalsOfDay([], null)).toEqual([])
  })
})
