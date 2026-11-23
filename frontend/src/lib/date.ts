const WEEKDAYS = '일월화수목금토'

/**
 * '2026-11-20' → '11월 20일 (금)'. 화면 머리말처럼 사람이 읽는 자리에 쓴다.
 * 형식이 다르면 받은 문자열을 그대로 돌려준다(빈 칸으로 만들지 않는다).
 *
 * 요일은 날짜 자체로 계산한다 — new Date('2026-11-20') 은 UTC 자정이라
 * 시간대에 따라 하루가 밀릴 수 있어 Date.UTC 로 만든 뒤 UTC 요일을 읽는다.
 */
export function formatKoDate(iso?: string | null): string {
  if (!iso) return ''
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  if (!m) return iso
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])]
  const wd = new Date(Date.UTC(y, mo - 1, d)).getUTCDay()
  return `${mo}월 ${d}일 (${WEEKDAYS[wd]})`
}
