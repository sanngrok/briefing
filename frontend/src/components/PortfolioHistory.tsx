import { useMemo, useState } from 'react'
import {
  Area,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  CartesianGrid,
} from 'recharts'
import { sliceRange, summarize } from '../lib/history'
import type { HistoryRange, Snapshot } from '../lib/history'
import { direction, formatPct, formatSigned, formatWon } from '../lib/portfolio'

const RANGES: { key: HistoryRange; label: string }[] = [
  { key: '1W', label: '1주' },
  { key: '1M', label: '1개월' },
  { key: '3M', label: '3개월' },
  { key: 'ALL', label: '전체' },
]

const RANGE_TEXT: Record<HistoryRange, string> = {
  '1W': '최근 1주',
  '1M': '최근 1개월',
  '3M': '최근 3개월',
  ALL: '기록 전체',
}

// SVG 속성은 CSS 변수를 못 받아 index.css 팔레트 값을 그대로 쓴다.
const UP = '#f04452'
const DOWN = '#3182f6'
const GRID = '#f2f4f6'
const TICK = '#8b95a1'
const COST = '#b0b8c1'

/** 487만 · 1.2억 — 축에는 짧게 */
function compactWon(v: number): string {
  if (Math.abs(v) >= 1e8) return `${(v / 1e8).toFixed(1).replace(/\.0$/, '')}억`
  if (Math.abs(v) >= 1e4) return `${Math.round(v / 1e4).toLocaleString('ko-KR')}만`
  return Math.round(v).toLocaleString('ko-KR')
}

function shortDate(d: string): string {
  return `${Number(d.slice(5, 7))}.${Number(d.slice(8, 10))}`
}

/**
 * 내 자산 추이. 하루 한 점(총 평가금액)을 선으로, 매입금액을 점선으로 그린다 —
 * 두 선의 간격이 평가손익이고, 점선이 계단처럼 뛰면 그날 사고판 것이다.
 */
export function PortfolioHistory({ history, today }: { history: Snapshot[]; today: string }) {
  const [range, setRange] = useState<HistoryRange>('1M')
  const points = useMemo(() => sliceRange(history, range, today), [history, range, today])
  const summary = summarize(points)
  const dir = summary ? direction(summary.change) : 'flat'
  const color = dir === 'down' ? DOWN : UP

  return (
    <section className="panel pf-history" aria-label="자산 추이">
      <div className="pf-head">
        <h2 className="pf-head-title">자산 추이</h2>
        <div className="segmented segmented-sm" role="group" aria-label="기간">
          {RANGES.map((r) => (
            <button
              key={r.key}
              type="button"
              className={`seg${range === r.key ? ' active' : ''}`}
              aria-pressed={range === r.key}
              onClick={() => setRange(r.key)}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {summary ? (
        <>
          <p className="pf-history-sum">
            <span className="pf-history-range">{RANGE_TEXT[range]}</span>
            <span className={`pf-history-change mono dir-${dir}`}>
              {formatSigned(summary.change)}원 ({formatPct(summary.changePct)})
            </span>
          </p>
          {Math.round(summary.costChange) !== 0 && (
            <p className="pf-history-note mono">
              그 사이 매입금액 {formatSigned(summary.costChange)}원 · 이를 뺀 평가 변동{' '}
              <span className={`dir-${direction(summary.gain)}`}>{formatSigned(summary.gain)}원</span>
            </p>
          )}

          <div className="pf-history-chart">
            <ResponsiveContainer width="100%" height={220}>
              <ComposedChart data={points} margin={{ top: 10, right: 4, bottom: 0, left: -6 }}>
                <defs>
                  <linearGradient id="pf-history-fill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={color} stopOpacity={0.16} />
                    <stop offset="100%" stopColor={color} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} stroke={GRID} />
                <XAxis
                  dataKey="date"
                  tickFormatter={shortDate}
                  tick={{ fontSize: 12, fill: TICK }}
                  axisLine={false}
                  tickLine={false}
                  tickMargin={8}
                  minTickGap={20}
                />
                <YAxis
                  domain={['auto', 'auto']}
                  tickFormatter={compactWon}
                  tick={{ fontSize: 12, fill: TICK }}
                  axisLine={false}
                  tickLine={false}
                  width={52}
                />
                <Tooltip
                  cursor={{ stroke: '#d1d6db', strokeDasharray: '3 3' }}
                  formatter={(v: number, name: string) => [`${formatWon(v)}원`, name]}
                  labelFormatter={(d: string) => d}
                  contentStyle={{
                    fontSize: 13,
                    borderRadius: 14,
                    border: 'none',
                    padding: '10px 14px',
                    boxShadow: '0 8px 24px rgba(0, 29, 58, 0.12)',
                  }}
                  labelStyle={{ color: TICK, marginBottom: 4 }}
                />
                <Line
                  type="stepAfter"
                  dataKey="cost"
                  name="매입금액"
                  stroke={COST}
                  strokeWidth={1.5}
                  strokeDasharray="4 4"
                  dot={false}
                  activeDot={false}
                />
                <Area
                  type="monotone"
                  dataKey="value"
                  name="평가금액"
                  stroke={color}
                  strokeWidth={2.5}
                  fill="url(#pf-history-fill)"
                  dot={points.length <= 10 ? { r: 3, strokeWidth: 0, fill: color } : false}
                  activeDot={{ r: 5, strokeWidth: 3, stroke: '#fff' }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <p className="pf-history-legend">
            <span className="legend-line" style={{ background: color }} /> 평가금액
            <span className="legend-line legend-dash" /> 매입금액
          </p>
        </>
      ) : (
        <div className="pf-history-empty">
          <p className="pf-history-empty-title">
            {history.length === 0 ? '아직 기록이 없어요' : '기록이 쌓이는 중이에요'}
          </p>
          <p className="pf-history-empty-desc">
            사이트를 열거나 토스 동기화(평일 16:30)가 돌 때마다 그날 총 평가금액을 하루 한
            점씩 기록해요. 이틀 이상 쌓이면 그래프로 보여 드려요.
            {history.length > 0 &&
              ` 지금까지 ${history.length}일 기록됨 (마지막 ${history[history.length - 1].date}).`}
          </p>
        </div>
      )}
    </section>
  )
}
