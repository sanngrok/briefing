import type { ReactNode } from 'react'
import { PAGES, hashOf } from '../lib/route'
import type { Page } from '../lib/route'
import { formatKoDate } from '../lib/date'

// 24px 격자, 선 아이콘. currentColor 를 따라 메뉴별 색이 그대로 입혀진다.
const ICONS: Record<Page, ReactNode> = {
  home: (
    <path d="M3 10.5 12 3l9 7.5M5.5 8.5V20h4.5v-6h4v6h4.5V8.5" />
  ),
  assets: (
    <>
      <rect x="3" y="6" width="18" height="14" rx="3" />
      <path d="M16 13h2M3 10h18M7 6V4.5h10V6" />
    </>
  ),
  news: (
    <>
      <rect x="4" y="3.5" width="16" height="17" rx="2.5" />
      <path d="M8 8h8M8 12h8M8 16h5" />
    </>
  ),
  chart: (
    <path d="M4 4v16h16M7.5 15l3.5-4 3 2.5L19 8" />
  ),
  report: (
    <>
      <path d="M14 3.5H7.5A2.5 2.5 0 0 0 5 6v12a2.5 2.5 0 0 0 2.5 2.5h9A2.5 2.5 0 0 0 19 18V8.5z" />
      <path d="M14 3.5v5h5M9 13h6M9 16.5h4" />
    </>
  ),
}

/** 브랜드 마크 — 파비콘과 같은 그림. */
function LogoMark() {
  return (
    <svg className="sidenav-logo" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="10" fill="var(--accent)" />
      <path
        d="M8 20.5l5-5 4 3.5 7-8"
        fill="none"
        stroke="#fff"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/**
 * 화면 전환 메뉴. 넓은 화면에서는 왼쪽에 떠 있는 카드형 사이드바, 좁은 화면(폰)
 * 에서는 위에 붙는 가로 탭바가 된다 — 같은 마크업을 CSS 로만 바꾼다.
 *
 * 링크는 해시 앵커라서 뒤로가기·새 탭 열기가 브라우저 기본 동작 그대로 된다.
 */
export function SideNav({
  page,
  reportDate,
  badges,
}: {
  page: Page
  reportDate?: string
  /** 메뉴 옆에 띄울 숫자(0 이면 숨김) */
  badges?: Partial<Record<Page, number>>
}) {
  return (
    <aside className="sidenav">
      <div className="sidenav-brand">
        <a className="sidenav-title" href={hashOf('home')}>
          <LogoMark />
          AI 시그널 리포트
        </a>
        {reportDate && (
          <span className="date-pill" title={reportDate}>
            {formatKoDate(reportDate)} 브리핑
          </span>
        )}
      </div>

      <nav aria-label="화면 메뉴">
        <ul className="sidenav-list">
          {PAGES.map((p) => {
            const badge = badges?.[p.key] ?? 0
            return (
              <li key={p.key}>
                <a
                  className="sidenav-link"
                  data-page={p.key}
                  href={hashOf(p.key)}
                  aria-current={p.key === page ? 'page' : undefined}
                >
                  <span className="sidenav-icon-wrap">
                    <svg
                      className="sidenav-icon"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.9"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
                      {ICONS[p.key]}
                    </svg>
                  </span>
                  <span>{p.label}</span>
                  {badge > 0 && <span className="sidenav-badge mono">{badge}</span>}
                </a>
              </li>
            )
          })}
        </ul>
      </nav>

      <p className="sidenav-foot">정보 제공 목적이며 투자 판단의 근거가 아니에요.</p>
    </aside>
  )
}
