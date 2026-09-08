import type { Mover, Movers } from '../api/client'

// 등락률 |x| 가 이 값 이상이면 '급등락'으로 강조 (국내 대형주 기준 체감치)
const SHARP = 5

function Row({ mover, dir }: { mover: Mover; dir: 'up' | 'down' }) {
  const pct = mover.change_pct ?? 0
  const sharp = Math.abs(pct) >= SHARP
  return (
    <li className="mover-row">
      <span className="mover-name">
        {mover.name}
        {sharp && <span className={`mover-flag flag-${dir}`}>급{dir === 'up' ? '등' : '락'}</span>}
      </span>
      <span className="mover-close mono">
        {mover.close != null ? mover.close.toLocaleString('ko-KR') : '—'}
      </span>
      <span className={`mover-pct mono dir-${dir}`}>
        {dir === 'up' ? '▲' : '▼'} {Math.abs(pct).toFixed(2)}%
      </span>
    </li>
  )
}

function Column({
  title,
  items,
  dir,
}: {
  title: string
  items: Mover[]
  dir: 'up' | 'down'
}) {
  return (
    <div className="mover-col">
      <div className={`mover-col-title dir-${dir}`}>{title}</div>
      {items.length === 0 ? (
        <p className="mover-none">해당 종목이 없습니다.</p>
      ) : (
        <ul className="mover-list">
          {items.map((m) => (
            <Row key={m.symbol} mover={m} dir={dir} />
          ))}
        </ul>
      )}
    </div>
  )
}

export function MoversPanel({ movers }: { movers: Movers | null }) {
  if (!movers || (movers.gainers.length === 0 && movers.losers.length === 0)) {
    return <p className="empty">표시할 시세 데이터가 없습니다.</p>
  }
  return (
    <div className="panel">
      <div className="mover-grid">
        <Column title="상승" items={movers.gainers} dir="up" />
        <Column title="하락" items={movers.losers} dir="down" />
      </div>
      {movers.date && <div className="mover-date mono">{movers.date} 종가 기준</div>}
    </div>
  )
}
