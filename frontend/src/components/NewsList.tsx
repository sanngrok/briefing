import { useState } from 'react'
import type { NewsItem } from '../api/client'
import { LoadState } from './LoadState'
import type { Status } from './LoadState'
import { newsTone as tone } from '../lib/news'

export type NewsDirection = 'all' | 'good' | 'bad'

/** 방향별로 따로 받아 둔 목록. 서버가 각 방향 안에서 강한 순으로 뽑아 준다. */
export interface NewsLists {
  all: NewsItem[]
  good: NewsItem[]
  bad: NewsItem[]
}

export const NEWS_SHOWN = 12

const TABS: { key: NewsDirection; label: string }[] = [
  { key: 'all', label: '전체' },
  { key: 'good', label: '호재' },
  { key: 'bad', label: '악재' },
]

const EMPTY: Record<NewsDirection, string> = {
  all: '표시할 뉴스가 없어요.',
  good: '호재로 분류된 기사가 없어요.',
  bad: '악재로 분류된 기사가 없어요.',
}

function timeOf(iso?: string | null) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString('ko-KR', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function NewsList({
  lists,
  status,
  onRetry,
}: {
  lists: NewsLists
  status: Status
  onRetry?: () => void
}) {
  const [filter, setFilter] = useState<NewsDirection>('all')
  const items = (lists[filter] ?? []).slice(0, NEWS_SHOWN)

  return (
    <div>
      {/* 토스식 세그먼트 컨트롤 — 회색 홈 위로 흰 칸이 선택된 쪽을 가리킨다 */}
      <div className="segmented news-tabs" role="group" aria-label="뉴스 방향">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            className={`seg seg-${t.key}${filter === t.key ? ' active' : ''}`}
            onClick={() => setFilter(t.key)}
            aria-pressed={filter === t.key}
            disabled={status !== 'ready'}
          >
            {t.label}
          </button>
        ))}
      </div>

      {status !== 'ready' ? (
        <LoadState status={status} rows={4} onRetry={onRetry} label="뉴스를 불러오지 못했습니다." />
      ) : items.length === 0 ? (
        <p className="empty">{EMPTY[filter]}</p>
      ) : (
        <ul className="newslist">
          {items.map((n, i) => {
            const t = tone(n.sentiment)
            return (
              <li key={`${n.url ?? n.title}-${i}`} className="newsrow">
                <div className={`news-score ${t.cls}`}>{t.label}</div>

                <div className="news-body">
                  <div className="news-title">
                    {n.url ? (
                      <a href={n.url} target="_blank" rel="noopener noreferrer">
                        {n.title}
                      </a>
                    ) : (
                      n.title
                    )}
                  </div>

                  {n.summary && <p className="news-summary">{n.summary}</p>}

                  <div className="news-meta">
                    {n.name && <span className="news-ticker">{n.name}</span>}
                    {timeOf(n.published_at) && <span>{timeOf(n.published_at)}</span>}
                    {(n.issue_tags ?? []).slice(0, 3).map((tag) => (
                      <span key={tag} className="news-tag">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
