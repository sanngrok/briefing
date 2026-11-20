import { describe, expect, it } from 'vitest'
import { PAGES, hashOf, metaOf, pageFromHash } from './route'

describe('pageFromHash', () => {
  it('빈 해시는 첫 화면', () => {
    expect(pageFromHash('')).toBe('home')
    expect(pageFromHash('#')).toBe('home')
    expect(pageFromHash('#/')).toBe('home')
  })

  it('알려진 화면은 그대로', () => {
    expect(pageFromHash('#/assets')).toBe('assets')
    expect(pageFromHash('#/news')).toBe('news')
  })

  it('슬래시 없는 해시와 뒤에 붙은 경로·쿼리도 받아 준다', () => {
    expect(pageFromHash('#chart')).toBe('chart')
    expect(pageFromHash('#/report/2026-11-20')).toBe('report')
    expect(pageFromHash('#/news?dir=bad')).toBe('news')
  })

  it('모르는 값은 첫 화면으로', () => {
    expect(pageFromHash('#/nope')).toBe('home')
  })
})

describe('hashOf', () => {
  it('모든 화면이 해시를 거쳐 제자리로 돌아온다', () => {
    for (const p of PAGES) expect(pageFromHash(hashOf(p.key))).toBe(p.key)
  })

  it('첫 화면은 #/', () => {
    expect(hashOf('home')).toBe('#/')
  })
})

describe('metaOf', () => {
  it('화면별 제목을 돌려준다', () => {
    expect(metaOf('chart').title).toBe('종목 추이')
  })
})
