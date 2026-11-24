export type NewsToneClass = 'good-strong' | 'good' | 'bad-strong' | 'bad' | 'flat'

// 감정 점수 → 표시용 등급. 색과 라벨을 여기서 한 번에 결정한다.
// 색은 국내 관행을 따른다 — 호재(주가를 올릴 재료)는 빨강, 악재는 파랑.
//
// 점수 자체는 화면에 내보이지 않는다. 모델이 매기는 값이 사실상 몇 개로 몰려 있어
// (실측에서 0.8 이 최빈값) 소수 둘째 자리까지 보여주면 있지도 않은 정밀도를
// 주장하게 된다. 뒤쪽 시그널 판정은 여전히 점수로 돌아간다.
//
// ±0.15 경계는 서버의 NEWS_DIRECTION_THRESHOLD 와 같아야 한다 — 다르면 같은 기사가
// 목록에서는 '중립' 인데 악재 탭에 들어가는 일이 생긴다.
// 경계 ±0.6 은 기준표(SENTIMENT_SCALE)의 앵커를 따른다 — 그 위가 '호실적·목표주가
// 상향·대형 계약' 이상이다. 이번 주 분포에 맞춰 다시 잡지 않는 이유는, 라벨이
// 절대적인 뜻을 가져야 하기 때문이다. 큰 악재가 없던 주에는 '악재' 배지가 하나도
// 안 뜨는 게 맞다.
export function newsTone(sentiment?: number | null): { cls: NewsToneClass; label: string } {
  const s = sentiment ?? 0
  if (s >= 0.6) return { cls: 'good-strong', label: '호재' }
  if (s >= 0.15) return { cls: 'good', label: '약호재' }
  if (s <= -0.6) return { cls: 'bad-strong', label: '악재' }
  if (s <= -0.15) return { cls: 'bad', label: '약악재' }
  return { cls: 'flat', label: '중립' }
}

/** 목록 안의 호재·악재 개수(약호재·약악재 포함, 중립 제외). 홈 뉴스 카드의 요약 숫자. (순수) */
export function countTones(items: { sentiment?: number | null }[]): { good: number; bad: number } {
  let good = 0
  let bad = 0
  for (const n of items) {
    const c = newsTone(n.sentiment).cls
    if (c.startsWith('good')) good += 1
    else if (c.startsWith('bad')) bad += 1
  }
  return { good, bad }
}
