import { describe, expect, it } from 'vitest'
import {
  alertCurrency,
  alertPrice,
  buildAlertRows,
  evaluateAlert,
  formatAlertPrice,
  isHit,
  notifyKey,
  parseAlerts,
  pruneNotified,
  setAlert,
  toSecretLine,
  validateAlertInput,
} from './alerts'

describe('alertCurrency / alertPrice', () => {
  it('국내 6자리는 원, 나머지는 달러', () => {
    expect(alertCurrency('005930')).toBe('KRW')
    expect(alertCurrency('PLTR')).toBe('USD')
  })

  it('해외 종목은 원화 현재가를 환율로 되돌린다', () => {
    expect(alertPrice('005930', 180000, 1400)).toBe(180000)
    expect(alertPrice('PLTR', 280000, 1400)).toBe(200)
  })

  it('해외 종목인데 환율이 없거나 시세가 없으면 판정하지 않는다', () => {
    expect(alertPrice('PLTR', 280000, null)).toBeNull()
    expect(alertPrice('PLTR', 280000, 0)).toBeNull()
    expect(alertPrice('005930', null, 1400)).toBeNull()
  })
})

describe('evaluateAlert', () => {
  const both = { stop: 170000, target: 250000 }

  it('도달', () => {
    expect(evaluateAlert(250000, both).kind).toBe('target-hit')
    expect(evaluateAlert(260000, both).kind).toBe('target-hit')
    expect(evaluateAlert(170000, both).kind).toBe('stop-hit')
    expect(evaluateAlert(150000, both).kind).toBe('stop-hit')
  })

  it('3% 안으로 다가오면 근접', () => {
    expect(evaluateAlert(244000, both).kind).toBe('near-target') // 2.46% 남음
    expect(evaluateAlert(175000, both).kind).toBe('near-stop') // 2.86% 남음
    expect(evaluateAlert(200000, both).kind).toBe('watching')
  })

  it('남은 거리와 위치', () => {
    const s = evaluateAlert(200000, both)
    expect(s.toTarget).toBeCloseTo(25)
    expect(s.toStop).toBeCloseTo(15)
    expect(s.position).toBeCloseTo(30000 / 80000)
    expect(evaluateAlert(300000, both).position).toBe(1)
  })

  it('한쪽만 걸어도 된다', () => {
    expect(evaluateAlert(100, { target: 102 }).kind).toBe('near-target')
    expect(evaluateAlert(100, { target: 102 }).position).toBeNull()
    expect(evaluateAlert(100, { stop: 100 }).kind).toBe('stop-hit')
    expect(evaluateAlert(100, { stop: 100 }).toTarget).toBeNull()
  })

  it('둘 다 근접하면 더 가까운 쪽', () => {
    expect(evaluateAlert(100, { stop: 98, target: 101 }).kind).toBe('near-target')
    expect(evaluateAlert(100, { stop: 99.5, target: 102 }).kind).toBe('near-stop')
  })

  it('isHit', () => {
    expect(isHit('target-hit')).toBe(true)
    expect(isHit('near-stop')).toBe(false)
  })
})

describe('validateAlertInput', () => {
  it('콤마 입력을 받고, 한쪽만도 된다', () => {
    expect(validateAlertInput('250,000', '170,000')).toEqual({
      ok: true,
      setting: { target: 250000, stop: 170000 },
    })
    expect(validateAlertInput('', '170000')).toEqual({ ok: true, setting: { stop: 170000 } })
  })

  it('둘 다 비우면 해제', () => {
    expect(validateAlertInput(' ', '')).toEqual({ ok: true, setting: null })
  })

  it('잘못된 값은 이유와 함께 거절', () => {
    expect(validateAlertInput('abc', '').ok).toBe(false)
    expect(validateAlertInput('0', '').ok).toBe(false)
    expect(validateAlertInput('100', '200')).toEqual({
      ok: false,
      error: '목표가는 손절가보다 높아야 해요.',
    })
  })
})

describe('setAlert / parseAlerts', () => {
  it('설정하고 지운다(종목코드 정규화)', () => {
    const a = setAlert({}, '5930', { target: 1 })
    expect(a).toEqual({ '005930': { target: 1 } })
    expect(setAlert(a, '005930', null)).toEqual({})
  })

  it('파일의 {alerts} 도, 저장본 그대로도 읽고 깨진 값은 버린다', () => {
    const raw = {
      alerts: {
        '005930': { target: 250000, stop: 170000 },
        pltr: { target: '200' },
        BAD: { target: 1, stop: 5 },
        EMPTY: {},
        X: 'nope',
      },
    }
    expect(parseAlerts(raw)).toEqual({
      '005930': { target: 250000, stop: 170000 },
      PLTR: { target: 200 },
    })
    expect(parseAlerts({ TSLA: { stop: 300 } })).toEqual({ TSLA: { stop: 300 } })
    expect(parseAlerts([1, 2])).toEqual({})
    expect(parseAlerts(null)).toEqual({})
  })
})

describe('toSecretLine', () => {
  it('보유 종목 순서대로, 설정 있는 종목만 값을 붙인다', () => {
    const line = toSecretLine(['005930', 'TSLA', 'PLTR', 'TSLA'], {
      '005930': { stop: 170000, target: 250000 },
      PLTR: { target: 200.456 },
      AAPL: { target: 999 }, // 보유하지 않은 종목은 뺀다
    })
    expect(line).toBe('005930:stop=170000:target=250000,TSLA,PLTR:target=200.46')
  })
})

describe('formatAlertPrice', () => {
  it('원과 달러', () => {
    expect(formatAlertPrice(251000.4, 'KRW')).toBe('251,000원')
    expect(formatAlertPrice(201.3, 'USD')).toBe('$201.30')
    expect(formatAlertPrice(null, 'USD')).toBe('—')
  })
})

describe('notified keys', () => {
  it('오늘 것만 남긴다', () => {
    const keys = [notifyKey('2026-11-22', 'A', 'target-hit'), notifyKey('2026-11-23', 'A', 'stop-hit')]
    expect(pruneNotified(keys, '2026-11-23')).toEqual(['2026-11-23:A:stop-hit'])
  })
})

describe('buildAlertRows', () => {
  it('도달 → 근접 → 감시 → 미설정 순, 해외 종목은 달러로 판정', () => {
    const rows = [
      { symbol: '000660', name: 'SK하이닉스', close: 500000 },
      { symbol: '005930', name: '삼성전자', close: 180000 },
      { symbol: 'PLTR', name: '팔란티어', close: 280000, priceSource: 'imported' },
      { symbol: 'TSLA', name: '테슬라', close: 600000 },
    ]
    const alerts = {
      '005930': { target: 250000 }, // 감시
      PLTR: { target: 199 }, // $200 → 도달
      TSLA: { stop: 420 }, // 600000/1400 = $428.6 → 근접
    }
    const out = buildAlertRows(rows, alerts, 1400)
    expect(out.map((r) => r.symbol)).toEqual(['PLTR', 'TSLA', '005930', '000660'])
    expect(out[0]).toMatchObject({ currency: 'USD', price: 200, stale: true })
    expect(out[0].status?.kind).toBe('target-hit')
    expect(out[1].status?.kind).toBe('near-stop')
    expect(out[3]).toMatchObject({ setting: null, status: null })
  })

  it('환율이 없으면 해외 종목은 설정이 있어도 판정하지 않는다', () => {
    const out = buildAlertRows([{ symbol: 'PLTR', name: 'P', close: 1 }], { PLTR: { target: 1 } }, null)
    expect(out[0].status).toBeNull()
    expect(out[0].setting).toEqual({ target: 1 })
  })
})

describe('buildAlertRows — 환율 폴백', () => {
  it('현재 환율이 없으면 가져올 때 환율로 판정한다', () => {
    const out = buildAlertRows(
      [{ symbol: 'PLTR', name: 'P', close: 280000, fxAtImport: 1400 }],
      { PLTR: { target: 199 } },
      null,
    )
    expect(out[0].price).toBe(200)
    expect(out[0].status?.kind).toBe('target-hit')
  })
})
