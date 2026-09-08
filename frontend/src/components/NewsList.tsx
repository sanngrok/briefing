import type { NewsItem } from '../api/client'

// 감정 점수 → 표시용 등급. 색과 라벨을 여기서 한 번에 결정한다.
function tone(sentiment?: number | null) {
  const s = sentiment ?? 0
  if (s >= 0.5) return { cls: 'pos-strong', label: '긍정' }
  if (s >= 0.15) return { cls: 'pos', label: '약긍정' }
  if (s <= -0.5) return { cls: 'neg-strong', label: '부정' }
  if (s <= -0.15) return { cls: 'neg', label: '약부정' }
  return { cls: 'flat', label: '중립' }
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

export function NewsList({ items }: { items: NewsItem[] }) {
  if (items.length === 0) {
    return <p className="empty">표시할 뉴스가 없습니다.</p>
  }

  return (
    <ul className="newslist">
      {items.map((n, i) => {
        const t = tone(n.sentiment)
        const score = n.sentiment ?? null
        return (
          <li key={`${n.url ?? n.title}-${i}`} className="newsrow">
            <div className={`news-score ${t.cls}`}>
              <span className="news-score-num mono">
                {score === null ? '—' : (score > 0 ? '+' : '') + score.toFixed(2)}
              </span>
              <span className="news-score-label">{t.label}</span>
            </div>

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
        )
      })}
    </ul>
  )
}
