import { describe, expect, it } from 'vitest'
import { AVATAR_TONES, avatarTone, initialOf } from './avatar'

describe('avatarTone', () => {
  it('같은 이름은 늘 같은 색', () => {
    expect(avatarTone('삼성전자')).toBe(avatarTone('삼성전자'))
    expect(avatarTone(' 삼성전자 ')).toBe(avatarTone('삼성전자'))
  })

  it('정해 둔 색 안에서만 고른다 (등락색 빨강·파랑 제외)', () => {
    for (const name of ['삼성전자', 'SK하이닉스', '테슬라', 'PLTR', '', '현대차']) {
      expect(AVATAR_TONES).toContain(avatarTone(name))
    }
    expect(AVATAR_TONES).not.toContain('red')
    expect(AVATAR_TONES).not.toContain('blue')
  })

  it('여러 종목이 한 색으로 몰리지 않는다', () => {
    const names = ['삼성전자', 'SK하이닉스', '현대차', '기아', 'NAVER', '카카오', '셀트리온', 'LG화학']
    expect(new Set(names.map(avatarTone)).size).toBeGreaterThan(2)
  })
})

describe('initialOf', () => {
  it('첫 글자, 영문은 대문자', () => {
    expect(initialOf('삼성전자')).toBe('삼')
    expect(initialOf('SK하이닉스')).toBe('S')
    expect(initialOf(' tesla ')).toBe('T')
  })

  it('빈 이름은 물음표', () => {
    expect(initialOf('')).toBe('?')
    expect(initialOf('   ')).toBe('?')
  })
})
