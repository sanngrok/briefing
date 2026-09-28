import { useMemo, useState } from 'react'
import type { NewsItem } from '../api/client'

// 감정 점수 → 표시용 등급. 색과 라벨을 여기서 한 번에 결정한다.
// 색은 국내 관행을 따른다 — 호재(주가를 올릴 재료)는 빨강, 악재는 파랑.
//
// 점수 자체는 화면에 내보이지 않는다. 모델이 매기는 값이 사실상 몇 개로 몰려 있어
// (실측에서 0.8 이 최빈값) 소수 둘째 자리까지 보여주면 있지도 않은 정밀도를
// 주장하게 된다. 뒤쪽 시그널 판정은 여전히 점수로 돌아간다.
function tone(sentiment?: number | null) {
  const s = sentiment ?? 0
  if (s >= 0.5) return { cls: 'good-strong', label: '호재', group: 'good' as const }
  if (s >= 0.15) return { cls: 'good', label: '약호재', group: 'good' as const }
  if (s <= -0.5) return { cls: 'bad-strong', label: '악재', group: 'bad' as const }
  if (s <= -0.15) return { cls: 'bad', label: '약악재', group: 'bad' as const }
  return { cls: 'flat', label: '중립', group: 'flat' as const }
}

type Filter = 'all' | 'good' | 'bad'

// 서버가 |감정| 큰 순으로 넘겨주므로, 걸러낸 뒤에도 센 것부터 남는다.
// 필터 때문에 조회는 더 많이(50건) 하지만 화면에 까는 것은 이만큼이다.
export const NEWS_SHOWN = 12

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

export function NewsList({ items }: { items: NewsItem[] }) {
  const [filter, setFilter] = useState<Filter>('all')

  const { shown, counts } = useMemo(() => {
    const withTone = items.map((n) => ({ n, t: tone(n.sentiment) }))
    const counts = {
      all: withTone.length,
      good: withTone.filter((x) => x.t.group === 'good').length,
      bad: withTone.filter((x) => x.t.group === 'bad').length,
    }
    const matched =
      filter === 'all' ? withTone : withTone.filter((x) => x.t.group === filter)
    return { shown: matched.slice(0, NEWS_SHOWN), counts }
  }, [items, filter])

  if (items.length === 0) {
    return <p className="empty">표시할 뉴스가 없습니다.</p>
  }

  const tabs: { key: Filter; label: string; count: number }[] = [
    { key: 'all', label: '전체', count: counts.all },
    { key: 'good', label: '호재', count: counts.good },
    { key: 'bad', label: '악재', count: counts.bad },
  ]

  return (
    <div>
      <div className="tabs news-tabs">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            className={`tab tab-${t.key}${filter === t.key ? ' active' : ''}`}
            onClick={() => setFilter(t.key)}
            aria-pressed={filter === t.key}
          >
            {t.label} {t.count}
          </button>
        ))}
      </div>

      {shown.length === 0 ? (
        <p className="empty">
          {filter === 'good' ? '호재로 분류된 기사가 없습니다.' : '악재로 분류된 기사가 없습니다.'}
        </p>
      ) : (
        <ul className="newslist">
          {shown.map(({ n, t }, i) => (
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
                  {n.issue_tags.slice(0, 3).map((tag) => (
                    <span key={tag} className="news-tag">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
