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
  resolveFxRate,
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

  it('워치리스트 시세가 없으면 가져오기 스냅샷(importedClose)을 대신 쓴다', () => {
    const rows = computeRows(
      [holding({ symbol: 'PLTR', importedClose: 248900, importedChangePct: 0.53 })],
      [],
    )
    expect(rows[0].close).toBe(248900)
    expect(rows[0].changePct).toBe(0.53)
    expect(rows[0].priceSource).toBe('imported')
    expect(rows[0].value).toBe(2489000)   // 10주 × 248,900원
  })

  it('워치리스트 시세가 있으면 가져오기 스냅샷보다 우선한다', () => {
    const rows = computeRows(
      [holding({ importedClose: 1, importedChangePct: 1 })],
      [{ symbol: '005930', close: 77000, change_pct: 10 }],
    )
    expect(rows[0].close).toBe(77000)
    expect(rows[0].priceSource).toBe('live')
  })

  it('시세가 전혀 없으면 priceSource 는 null', () => {
    const rows = computeRows([holding({ symbol: '999999' })], [])
    expect(rows[0].priceSource).toBeNull()
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

  it('importedClose/importedChangePct 를 숫자일 때만 받아준다', () => {
    const [h] = parseHoldings([
      { symbol: 'PLTR', quantity: 1, avgPrice: 100, importedClose: 248900, importedChangePct: 0.53 },
    ])
    expect(h.importedClose).toBe(248900)
    expect(h.importedChangePct).toBe(0.53)

    const [h2] = parseHoldings([{ symbol: '005930', quantity: 1, avgPrice: 100, importedClose: 'x' }])
    expect(h2.importedClose).toBeUndefined()
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

// --- 해외(USD) 보유 종목 통화 처리 -----------------------------------
// 평단을 동기화 시점 환율로 원화 환산해 박제했더니, 평단은 과거 환율이고
// 현재가는 오늘 환율이라 수익률에 환율 변동이 섞였다(토스 +6.03% vs 우리 +4.70%).
// 원종목 통화로 두고 표시할 때 같은 환율로 환산하면 수익률에서 환율이 약분된다.

const USD_HOLDING = {
  id: 'toss-PLTR',
  symbol: 'PLTR',
  name: '팔란티어',
  quantity: 17,
  avgPrice: 178.89,
  currency: 'USD' as const,
  fxAtImport: 1372.18,
}

describe('resolveFxRate', () => {
  it('국내 종목은 항상 1', () => {
    expect(resolveFxRate({ ...USD_HOLDING, currency: 'KRW' }, 1355)).toBe(1)
    expect(resolveFxRate({ id: 'a', symbol: '005930', name: '삼성', quantity: 1, avgPrice: 1 }, 1355)).toBe(1)
  })

  it('USD 는 현재 환율을 우선한다', () => {
    expect(resolveFxRate(USD_HOLDING, 1355.05)).toBe(1355.05)
  })

  it('현재 환율이 없으면 가져오기 시점 환율로 떨어진다', () => {
    expect(resolveFxRate(USD_HOLDING, null)).toBe(1372.18)
    expect(resolveFxRate(USD_HOLDING, undefined)).toBe(1372.18)
    expect(resolveFxRate(USD_HOLDING, 0)).toBe(1372.18)
  })
})

describe('USD 보유 종목 평가', () => {
  // 서버는 해외 시세도 원화로 환산해 내려준다 ($189.67 x 1355.05)
  const quote = { symbol: 'PLTR', close: 189.67 * 1355.05, change_pct: -1.52 }

  it('평단을 현재 환율로 환산해 원화로 보여준다', () => {
    const [row] = computeRows([USD_HOLDING], [quote], 1355.05)
    expect(row.avgPriceKrw).toBeCloseTo(178.89 * 1355.05, 2)
    expect(row.cost).toBeCloseTo(17 * 178.89 * 1355.05, 2)
    expect(row.value).toBeCloseTo(17 * 189.67 * 1355.05, 2)
  })

  it('수익률에서 환율이 약분된다 — 증권사(달러 기준)와 일치한다', () => {
    const [row] = computeRows([USD_HOLDING], [quote], 1355.05)
    const usdReturn = ((189.67 - 178.89) / 178.89) * 100
    expect(row.returnPct).toBeCloseTo(usdReturn, 6)
  })

  it('환율이 달라져도 수익률은 그대로다', () => {
    const cheap = { symbol: 'PLTR', close: 189.67 * 1200, change_pct: -1.52 }
    const dear = { symbol: 'PLTR', close: 189.67 * 1500, change_pct: -1.52 }
    const a = computeRows([USD_HOLDING], [cheap], 1200)[0]
    const b = computeRows([USD_HOLDING], [dear], 1500)[0]
    expect(a.returnPct).toBeCloseTo(b.returnPct!, 6)
    expect(a.value).not.toBeCloseTo(b.value!, 2)   // 평가금액은 환율을 따라 움직인다
  })

  it('가져온 시세 폴백도 같은 환율로 환산한다', () => {
    const h = { ...USD_HOLDING, importedClose: 177.78 }
    const [row] = computeRows([h], [], 1355.05)
    expect(row.priceSource).toBe('imported')
    expect(row.close).toBeCloseTo(177.78 * 1355.05, 2)
  })

  it('국내 종목은 환율을 줘도 그대로다', () => {
    const krw = { id: 'a', symbol: '005930', name: '삼성전자', quantity: 2, avgPrice: 70000 }
    const [row] = computeRows([krw], [{ symbol: '005930', close: 80000, change_pct: 1 }], 1355.05)
    expect(row.avgPriceKrw).toBe(70000)
    expect(row.cost).toBe(140000)
  })
})

describe('parseHoldings — 통화', () => {
  it('환율이 함께 있으면 USD 로 읽는다', () => {
    const [h] = parseHoldings({ holdings: [USD_HOLDING] })
    expect(h.currency).toBe('USD')
    expect(h.fxAtImport).toBe(1372.18)
  })

  it('환율이 없는 USD 는 원화로 취급한다 — 환산할 길이 없기 때문', () => {
    const [h] = parseHoldings({ holdings: [{ ...USD_HOLDING, fxAtImport: undefined }] })
    expect(h.currency).toBeUndefined()
  })

  it('통화 표기가 없던 예전 저장본은 그대로 원화다', () => {
    const [h] = parseHoldings({
      holdings: [{ id: 'x', symbol: 'PLTR', name: '팔란티어', quantity: 17, avgPrice: 245471 }],
    })
    expect(h.currency).toBeUndefined()
    expect(h.avgPrice).toBe(245471)
  })
})

describe('mergeHolding — 통화가 섞일 때', () => {
  it('USD 보유에 원화로 추가 매수하면 먼저 원화로 눕힌다', () => {
    const added = { id: 'n', symbol: 'PLTR', name: '팔란티어', quantity: 3, avgPrice: 250000 }
    const merged = mergeHolding(USD_HOLDING, added, 1355.05)
    const baseKrw = 178.89 * 1355.05
    expect(merged.currency).toBeUndefined()
    expect(merged.avgPrice).toBeCloseTo((17 * baseKrw + 3 * 250000) / 20, 2)
  })

  it('통화가 같으면 기존처럼 수량가중 평단', () => {
    const base = { id: 'a', symbol: '005930', name: '삼성', quantity: 10, avgPrice: 70000 }
    const added = { id: 'b', symbol: '005930', name: '삼성', quantity: 10, avgPrice: 80000 }
    expect(mergeHolding(base, added).avgPrice).toBe(75000)
  })
})
