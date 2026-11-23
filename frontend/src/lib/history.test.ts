import { describe, expect, it } from 'vitest'
import {
  HISTORY_MAX,
  kstDate,
  mergeHistory,
  parseHistory,
  recordSnapshot,
  sliceRange,
  summarize,
} from './history'
import type { Snapshot } from './history'

const s = (date: string, value: number, cost = 100, at?: string): Snapshot => ({
  date,
  value,
  cost,
  ...(at ? { at } : {}),
})

describe('kstDate', () => {
  it('UTC 15시 이후는 한국 날짜로 다음 날', () => {
    expect(kstDate(new Date('2026-11-23T14:59:00Z'))).toBe('2026-11-23')
    expect(kstDate(new Date('2026-11-23T15:00:00Z'))).toBe('2026-11-24')
  })
})

describe('parseHistory', () => {
  it('배열이든 {history} 든 읽고, 깨진 점은 버리고 날짜순으로', () => {
    const raw = {
      history: [
        s('2026-11-20', 300),
        { date: '11/21', value: 1, cost: 1 },
        { date: '2026-11-19', value: 'x', cost: 1 },
        { date: '2026-11-18', value: 200, cost: -5 },
        s('2026-11-17', 100),
        null,
      ],
    }
    expect(parseHistory(raw).map((p) => p.date)).toEqual(['2026-11-17', '2026-11-20'])
    expect(parseHistory([s('2026-11-17', 1)])).toHaveLength(1)
    expect(parseHistory('oops')).toEqual([])
  })
})

describe('mergeHistory', () => {
  it('같은 날짜는 더 늦게 기록된 값을 쓴다', () => {
    const a = [s('2026-11-20', 100, 100, '2026-11-20T01:00:00Z')]
    const b = [s('2026-11-20', 200, 100, '2026-11-20T07:30:00Z'), s('2026-11-21', 300)]
    const merged = mergeHistory(a, b)
    expect(merged.map((p) => p.value)).toEqual([200, 300])
    // 순서를 바꿔도 결과가 같다
    expect(mergeHistory(b, a).map((p) => p.value)).toEqual([200, 300])
  })

  it('기록 시각이 없는 옛 점은 시각이 있는 점에 진다', () => {
    const merged = mergeHistory([s('2026-11-20', 1, 1, '2026-11-20T00:00:00Z')], [s('2026-11-20', 2)])
    expect(merged[0].value).toBe(1)
  })

  it('너무 많으면 오래된 점부터 버린다', () => {
    const many = Array.from({ length: HISTORY_MAX + 5 }, (_, i) => {
      const d = new Date(Date.UTC(2020, 0, 1 + i)).toISOString().slice(0, 10)
      return s(d, i)
    })
    const merged = mergeHistory([], many)
    expect(merged).toHaveLength(HISTORY_MAX)
    expect(merged[0].value).toBe(5)
  })
})

describe('recordSnapshot', () => {
  it('값이 그대로면 같은 배열(저장 생략)', () => {
    const h = [s('2026-11-23', 1000.2, 900)]
    expect(recordSnapshot(h, s('2026-11-23', 1000.4, 900, 'x'))).toBe(h)
  })

  it('같은 날 값이 바뀌면 덮어쓰고, 새 날이면 붙인다', () => {
    const h = [s('2026-11-22', 900, 900, 'a'), s('2026-11-23', 1000, 900, 'a')]
    expect(recordSnapshot(h, s('2026-11-23', 1100, 900, 'b')).map((p) => p.value)).toEqual([
      900, 1100,
    ])
    expect(recordSnapshot(h, s('2026-11-24', 1200, 900, 'b'))).toHaveLength(3)
  })
})

describe('sliceRange', () => {
  const h = [s('2026-10-01', 1), s('2026-11-10', 2), s('2026-11-17', 3), s('2026-11-23', 4)]
  it('오늘 포함 7일 / 30일 / 전체', () => {
    expect(sliceRange(h, '1W', '2026-11-23').map((p) => p.value)).toEqual([3, 4])
    expect(sliceRange(h, '1M', '2026-11-23').map((p) => p.value)).toEqual([2, 3, 4])
    expect(sliceRange(h, '3M', '2026-11-23')).toHaveLength(4)
    expect(sliceRange(h, 'ALL', '2026-11-23')).toBe(h)
  })
})

describe('summarize', () => {
  it('점이 2개 미만이면 null', () => {
    expect(summarize([])).toBeNull()
    expect(summarize([s('2026-11-23', 1)])).toBeNull()
  })

  it('추가 매수로 늘어난 몫과 수익으로 늘어난 몫을 가른다', () => {
    // 100만 → 160만. 그 사이 50만을 더 샀다 → 순수 평가 변동은 +10만
    const r = summarize([s('2026-11-01', 1_000_000, 1_000_000), s('2026-11-23', 1_600_000, 1_500_000)])!
    expect(r.change).toBe(600_000)
    expect(r.changePct).toBeCloseTo(60)
    expect(r.costChange).toBe(500_000)
    expect(r.gain).toBe(100_000)
  })
})
