/**
 * 종목 아바타 — 토스증권 목록의 종목 로고 자리를 이름 첫 글자 동그라미로 대신한다.
 *
 * 색은 이름에서 결정적으로 고른다(새로고침해도 같은 종목은 같은 색).
 * 빨강·파랑은 빼 두었다. 이 화면에서 둘은 상승·하락을 뜻하므로, 아바타가
 * 빨갛다고 오른 종목처럼 읽히면 안 된다.
 */
export const AVATAR_TONES = ['teal', 'green', 'orange', 'purple', 'yellow'] as const
export type AvatarTone = (typeof AVATAR_TONES)[number]

export function avatarTone(name: string): AvatarTone {
  let h = 0
  for (const ch of name.trim()) h = (h * 31 + (ch.codePointAt(0) ?? 0)) >>> 0
  return AVATAR_TONES[h % AVATAR_TONES.length]
}

/** 'SK하이닉스' → 'S', '삼성전자' → '삼', 'tesla' → 'T'. 비면 '?' */
export function initialOf(name: string): string {
  const first = [...name.trim()][0]
  return first ? first.toUpperCase() : '?'
}
