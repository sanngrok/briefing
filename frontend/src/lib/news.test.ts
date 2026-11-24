import { describe, expect, it } from 'vitest'
import { countTones, newsTone } from './news'

describe('newsTone', () => {
  it('±0.6 은 호재·악재, ±0.15 는 약호재·약악재, 그 사이는 중립', () => {
    expect(newsTone(0.8).label).toBe('호재')
    expect(newsTone(0.15).label).toBe('약호재')
    expect(newsTone(0.1).label).toBe('중립')
    expect(newsTone(-0.15).label).toBe('약악재')
    expect(newsTone(-0.6).label).toBe('악재')
    expect(newsTone(null).cls).toBe('flat')
  })
})

describe('countTones', () => {
  it('약호재·약악재까지 세고 중립은 뺀다', () => {
    const items = [0.8, 0.2, 0.0, -0.3, -0.9, null].map((sentiment) => ({ sentiment }))
    expect(countTones(items)).toEqual({ good: 2, bad: 2 })
    expect(countTones([])).toEqual({ good: 0, bad: 0 })
  })
})
