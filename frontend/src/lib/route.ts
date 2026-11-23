/**
 * 화면 전환은 주소의 해시(#/assets)로 한다. 라우터 라이브러리를 들이지 않은 이유:
 *   - 화면이 다섯 개뿐이고 중첩 경로가 없다.
 *   - 해시는 서버로 가지 않아 Vercel 에 rewrite 설정이 필요 없다.
 *   - 그래도 뒤로가기·새로고침·링크 공유(메일에서 특정 화면 열기)는 된다.
 */
export type Page = 'home' | 'assets' | 'news' | 'chart' | 'report'

export interface PageMeta {
  key: Page
  /** 사이드바·탭바에 쓰는 짧은 이름 */
  label: string
  /** 화면 맨 위 제목 */
  title: string
  /** 제목 아래 한 줄 설명 */
  desc: string
}

export const PAGES: PageMeta[] = [
  {
    key: 'home',
    label: '오늘 요약',
    title: '오늘 요약',
    desc: '국내 주식 뉴스 감정을 매일 분석해서 급하게 바뀐 종목을 찾아 드려요.',
  },
  {
    key: 'assets',
    label: '내 자산',
    title: '내 자산',
    desc: '보유 종목은 이 브라우저에만 저장되고 서버로 보내지 않아요.',
  },
  {
    key: 'news',
    label: '뉴스',
    title: '뉴스',
    desc: '감정이 강한 기사부터 보여 드려요. 호재와 악재를 나눠 볼 수도 있어요.',
  },
  {
    key: 'chart',
    label: '종목 차트',
    title: '종목 추이',
    desc: '종가와 그날 뉴스의 평균 감정을 한 차트에서 함께 봐요.',
  },
  {
    key: 'report',
    label: '리포트',
    title: '일일 리포트',
    desc: '평일 아침 7시, 직전 장 마감과 밤사이 뉴스로 만든 AI 브리핑이에요.',
  },
]

const KEYS = new Set<string>(PAGES.map((p) => p.key))

/** '#/assets' → 'assets'. 비었거나 모르는 값이면 첫 화면으로. */
export function pageFromHash(hash: string): Page {
  const key = hash.replace(/^#\/?/, '').split(/[/?]/)[0]
  return KEYS.has(key) ? (key as Page) : 'home'
}

export function hashOf(page: Page): string {
  return page === 'home' ? '#/' : `#/${page}`
}

export function metaOf(page: Page): PageMeta {
  return PAGES.find((p) => p.key === page) ?? PAGES[0]
}
