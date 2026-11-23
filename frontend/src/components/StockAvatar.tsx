import { avatarTone, initialOf } from '../lib/avatar'

/** 종목 이름 첫 글자를 담은 파스텔 동그라미. 장식이라 스크린리더에는 숨긴다. */
export function StockAvatar({ name, size = 'md' }: { name: string; size?: 'sm' | 'md' | 'lg' }) {
  return (
    <span className={`avatar avatar-${size} tone-${avatarTone(name)}`} aria-hidden="true">
      {initialOf(name)}
    </span>
  )
}
