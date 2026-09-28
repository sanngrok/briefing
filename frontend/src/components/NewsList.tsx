import { useState } from 'react'
import type { NewsItem } from '../api/client'

// 감정 점수 → 표시용 등급. 색과 라벨을 여기서 한 번에 결정한다.
// 색은 국내 관행을 따른다 — 호재(주가를 올릴 재료)는 빨강, 악재는 파랑.
//
// 점수 자체는 화면에 내보이지 않는다. 모델이 매기는 값이 사실상 몇 개로 몰려 있어
// (실측에서 0.8 이 최빈값) 소수 둘째 자리까지 보여주면 있지도 않은 정밀도를
// 주장하게 된다. 뒤쪽 시그널 판정은 여전히 점수로 돌아간다.
//
// ±0.15 경계는 서버의 NEWS_DIRECTION_THRESHOLD 와 같아야 한다 — 다르면 같은 기사가
// 목록에서는 '중립' 인데 악재 탭에 들어가는 일이 생긴다.
function tone(sentiment?: number | null) {
  const s = sentiment ?? 0
  if (s >= 0.5) return { cls: 'good-strong', label: '호재' }
  if (s >= 0.15) return { cls: 'good', label: '약호재' }
  if (s <= -0.5) return { cls: 'bad-strong', label: '악재' }
  if (s <= -0.15) return { cls: 'bad', label: '약악재' }
  return { cls: 'flat', label: '중립' }
}

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
  all: '표시할 뉴스가 없습니다.',
  good: '호재로 분류된 기사가 없습니다.',
  bad: '악재로 분류된 기사가 없습니다.',
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

export function NewsList({ lists }: { lists: NewsLists }) {
  const [filter, setFilter] = useState<NewsDirection>('all')
  const items = (lists[filter] ?? []).slice(0, NEWS_SHOWN)

  return (
    <div>
      <div className="tabs news-tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            className={`tab tab-${t.key}${filter === t.key ? ' active' : ''}`}
            onClick={() => setFilter(t.key)}
            aria-pressed={filter === t.key}
          >
            {t.label}
          </button>
        ))}
      </div>

      {items.length === 0 ? (
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
