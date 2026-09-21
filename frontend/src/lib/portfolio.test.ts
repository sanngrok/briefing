// 포트폴리오 순수 함수 단위 테스트 (vitest)
//   실행: cd frontend && npm test
// 평가 계산·검증·저장본 파싱을 UI 없이 고정한다.

import { describe, expect, it } from 'vitest'
import {
  computeRows,
  computeTotals,
  direction,
  findDuplicate,
  formatPct,
  formatSigned,
  formatWon,
  mergeHolding,
  normalizeSymbol,
  parseHoldings,
  parseNumber,
  previousClose,
  serializeHoldings,
  sortByReturn,
  validateHolding,
} from './portfolio'
import type { Holding } from './portfolio'

const holding = (over: Partial<Holding> = {}): Holding => ({
  id: 'h1',
  symbol: '005930',
  name: '삼성전자',
  quantity: 10,
  avgPrice: 70000,
  ...over,
})

describe('normalizeSymbol', () => {
  it('국내 종목코드를 6자리로 맞춘다', () => {
    expect(normalizeSymbol('5930')).toBe('005930')
    expect(normalizeSymbol(' 005930 ')).toBe('005930')
  })

  it('숫자가 아닌 티커는 대문자로만 정리한다', () => {
    expect(normalizeSymbol('aapl')).toBe('AAPL')
  })

  it('빈 입력은 빈 문자열', () => {
    expect(normalizeSymbol('   ')).toBe('')
  })
})

describe('parseNumber', () => {
  it('콤마가 섞인 숫자를 받아준다', () => {
    expect(parseNumber('1,234.5')).toBe(1234.5)
  })

  it('숫자가 아니면 null', () => {
    expect(parseNumber('abc')).toBeNull()
    expect(parseNumber('')).toBeNull()
  })
})

describe('validateHolding', () => {
  const base = { symbol: '005930', name: '삼성전자', quantity: '10', avgPrice: '70000' }

  it('정상 입력은 Holding 으로 정규화된다', () => {
    const r = validateHolding(base, 'id-1')
    expect(r.ok).toBe(true)
    if (r.ok) {
      expect(r.holding).toEqual({
        id: 'id-1',
        symbol: '005930',
        name: '삼성전자',
        quantity: 10,
        avgPrice: 70000,
      })
    }
  })

  it('종목명을 비우면 종목코드로 대체한다', () => {
    const r = validateHolding({ ...base, name: '  ' }, 'id-1')
    expect(r.ok && r.holding.name).toBe('005930')
  })

  it('종목코드가 없으면 거부', () => {
    const r = validateHolding({ ...base, symbol: '' }, 'id-1')
    expect(r.ok).toBe(false)
  })

  it('수량 0 이하는 거부 (경계값)', () => {
    expect(validateHolding({ ...base, quantity: '0' }, 'x').ok).toBe(false)
    expect(validateHolding({ ...base, quantity: '-1' }, 'x').ok).toBe(false)
    expect(validateHolding({ ...base, quantity: '0.5' }, 'x').ok).toBe(true)
  })

  it('평단 0 은 허용, 음수는 거부 (무상증자 등 경계값)', () => {
    expect(validateHolding({ ...base, avgPrice: '0' }, 'x').ok).toBe(true)
    expect(validateHolding({ ...base, avgPrice: '-1' }, 'x').ok).toBe(false)
  })

  it('숫자가 아닌 수량은 한국어 메시지로 거부', () => {
    const r = validateHolding({ ...base, quantity: '열개' }, 'x')
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toContain('수량')
  })
})

describe('findDuplicate / mergeHolding', () => {
  it('같은 종목을 찾되 수정 중인 자신은 제외한다', () => {
    const list = [holding()]
    expect(findDuplicate(list, '5930')?.id).toBe('h1')     // 정규화 후 비교
    expect(findDuplicate(list, '005930', 'h1')).toBeUndefined()
  })

  it('추가 매수는 수량가중 평단으로 합쳐진다', () => {
    const merged = mergeHolding(
      holding({ quantity: 10, avgPrice: 70000 }),
      holding({ id: 'h2', quantity: 10, avgPrice: 50000 }),
    )
    expect(merged.quantity).toBe(20)
    expect(merged.avgPrice).toBe(60000)
    expect(merged.id).toBe('h1')     // 기존 행을 유지
  })
})

describe('previousClose', () => {
  it('등락률로 전일 종가를 역산한다', () => {
    expect(previousClose(110, 10)).toBeCloseTo(100, 6)
    expect(previousClose(90, -10)).toBeCloseTo(100, 6)
  })

  it('등락률이 없거나 -100% 이하면 역산 불가', () => {
    expect(previousClose(100, null)).toBeNull()
    expect(previousClose(100, -100)).toBeNull()
  })
})

describe('computeRows', () => {
  it('시세를 붙여 평가금액·손익·수익률·비중을 계산한다', () => {
    const rows = computeRows(
      [holding()],   // 10주 × 70,000원 = 700,000원
      [{ symbol: '005930', close: 77000, change_pct: 10 }],
    )
    const r = rows[0]
    expect(r.cost).toBe(700000)
    expect(r.value).toBe(770000)
    expect(r.pnl).toBe(70000)
    expect(r.returnPct).toBeCloseTo(10, 6)
    expect(r.dayPnl).toBeCloseTo(70000, 6)   // 전일 70,000 → 77,000
    expect(r.weight).toBeCloseTo(100, 6)     // 한 종목이면 비중 100%
  })

  it('시세가 없는 종목은 평가값이 전부 null (워치리스트 밖 종목)', () => {
    const rows = computeRows([holding({ symbol: '999999' })], [])
    expect(rows[0].close).toBeNull()
    expect(rows[0].value).toBeNull()
    expect(rows[0].pnl).toBeNull()
    expect(rows[0].returnPct).toBeNull()
    expect(rows[0].cost).toBe(700000)        // 매입금액은 시세 없이도 계산된다
  })

  it('비중은 평가금액 합계 기준으로 나뉜다', () => {
    const rows = computeRows(
      [holding({ id: 'a', symbol: '005930' }), holding({ id: 'b', symbol: '000660' })],
      [
        { symbol: '005930', close: 30000, change_pct: 0 },   // 300,000
        { symbol: '000660', close: 10000, change_pct: 0 },   // 100,000
      ],
    )
    expect(rows[0].weight).toBeCloseTo(75, 6)
    expect(rows[1].weight).toBeCloseTo(25, 6)
  })

  it('종목코드 표기가 달라도(앞자리 0 누락) 시세가 붙는다', () => {
    const rows = computeRows([holding()], [{ symbol: '5930', close: 70000, change_pct: 0 }])
    expect(rows[0].close).toBe(70000)
  })
})

describe('computeTotals', () => {
  it('수익률 분모는 시세가 있는 종목의 매입금액만 쓴다', () => {
    const rows = computeRows(
      [
        holding({ id: 'a', symbol: '005930' }),                  // 700,000 매입 / 시세 있음
        holding({ id: 'b', symbol: '999999', avgPrice: 50000 }), // 500,000 매입 / 시세 없음
      ],
      [{ symbol: '005930', close: 77000, change_pct: 0 }],
    )
    const t = computeTotals(rows)
    expect(t.cost).toBe(1200000)        // 전체 매입금액에는 미평가분도 포함
    expect(t.pricedCost).toBe(700000)
    expect(t.value).toBe(770000)
    expect(t.pnl).toBe(70000)
    expect(t.returnPct).toBeCloseTo(10, 6)   // 미평가분이 수익률을 왜곡하지 않는다
    expect(t.unpricedCount).toBe(1)
    expect(t.count).toBe(2)
  })

  it('빈 목록은 0 과 null', () => {
    const t = computeTotals([])
    expect(t.cost).toBe(0)
    expect(t.value).toBe(0)
    expect(t.returnPct).toBeNull()
  })
})

describe('sortByReturn', () => {
  it('수익률 내림차순, 평가 불가는 뒤로', () => {
    const rows = computeRows(
      [
        holding({ id: 'a', symbol: '005930' }),
        holding({ id: 'b', symbol: '000660' }),
        holding({ id: 'c', symbol: '999999' }),   // 시세 없음
      ],
      [
        { symbol: '005930', close: 60000, change_pct: 0 },   // -14%
        { symbol: '000660', close: 80000, change_pct: 0 },   // +14%
      ],
    )
    expect(sortByReturn(rows).map((r) => r.id)).toEqual(['b', 'a', 'c'])
  })
})

describe('parseHoldings', () => {
  it('내보낸 JSON 을 그대로 되읽는다 (round-trip)', () => {
    const list = [holding()]
    const restored = parseHoldings(JSON.parse(serializeHoldings(list)))
    expect(restored).toEqual(list)
  })

  it('배열만 있는 옛 형태도 받아준다', () => {
    expect(parseHoldings([{ symbol: '005930', quantity: 1, avgPrice: 100 }])).toHaveLength(1)
  })

  it('깨진 항목은 버리고 중복 종목은 1건만 남긴다', () => {
    const out = parseHoldings([
      { symbol: '005930', quantity: 1, avgPrice: 100 },
      { symbol: '005930', quantity: 2, avgPrice: 200 },   // 중복
      { symbol: '', quantity: 1, avgPrice: 100 },         // 코드 없음
      { symbol: '000660', quantity: 0, avgPrice: 100 },   // 수량 0
      { symbol: '035420', quantity: 1, avgPrice: -5 },    // 음수 평단
      'garbage',
      null,
    ])
    expect(out.map((h) => h.symbol)).toEqual(['005930'])
    expect(out[0].quantity).toBe(1)
  })

  it('형태가 아니면 빈 배열', () => {
    expect(parseHoldings(null)).toEqual([])
    expect(parseHoldings({ foo: 1 })).toEqual([])
  })
})

describe('표시 포맷', () => {
  it('금액은 원화 천단위, 손익은 부호를 붙인다', () => {
    expect(formatWon(1234567.4)).toBe('1,234,567')
    expect(formatWon(null)).toBe('—')
    expect(formatSigned(1000)).toBe('+1,000')
    expect(formatSigned(-1000)).toBe('−1,000')
    expect(formatSigned(0)).toBe('0')
  })

  it('수익률은 소수 2자리 + 부호', () => {
    expect(formatPct(12.345)).toBe('+12.35%')
    expect(formatPct(-1)).toBe('−1.00%')
    expect(formatPct(null)).toBe('—')
  })

  it('비중처럼 부호가 의미 없는 값은 signed=false 로 뺀다', () => {
    expect(formatPct(72.7, 1, false)).toBe('72.7%')
  })

  it('방향은 국내 관행(상승/하락) 클래스와 짝', () => {
    expect(direction(1)).toBe('up')
    expect(direction(-1)).toBe('down')
    expect(direction(0)).toBe('flat')
    expect(direction(null)).toBe('flat')
  })
})
