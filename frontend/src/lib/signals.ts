import type { Signal } from '../api/client'

/**
 * 하루치 시그널만 고른다. (순수 함수)
 *
 * /api/signals 는 날짜를 안 주면 전체 이력을 돌려준다. 예전 화면은 그걸 그대로
 * "오늘의 시그널"로 그려서, 운영이 쌓이자 266건(두 달치)이 오늘 것처럼 보였다.
 *
 * 기준일은 리포트 날짜다. 시그널이 0건인 날에도 리포트는 생기므로, '가장 최근
 * 시그널 날짜'로 고르면 잠잠한 날에 지난 시그널을 오늘 것으로 보여 주게 된다.
 * 리포트를 아직 못 받았거나 실패했을 때만 가장 최근 시그널 날짜로 대신한다.
 */
export function signalsOfDay(signals: Signal[], day?: string | null): Signal[] {
  const target = day ?? latestDate(signals)
  if (!target) return []
  return signals.filter((s) => s.date === target)
}

function latestDate(signals: Signal[]): string | undefined {
  let latest: string | undefined
  for (const s of signals) if (!latest || s.date > latest) latest = s.date
  return latest
}
