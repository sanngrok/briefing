import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts'
import type { MetricPoint } from '../api/client'

// 라이트/다크 양쪽에서 읽히는 중립 색상 (SVG 속성은 CSS 변수를 못 받으므로 고정값)
const GRID = 'rgba(148,163,184,0.25)'
const TICK = '#94a3b8'
const PRICE = '#3b82f6'
const SENT = '#22c55e'

export function SentimentChart({ data }: { data: MetricPoint[] }) {
  if (data.length === 0) {
    return <p className="empty">표시할 시세 데이터가 없습니다.</p>
  }
  return (
    <ResponsiveContainer width="100%" height={320}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
        <XAxis dataKey="date" tick={{ fontSize: 12, fill: TICK }} stroke={GRID} />
        <YAxis yAxisId="price" tick={{ fontSize: 12, fill: TICK }} stroke={GRID} />
        <YAxis
          yAxisId="sent"
          orientation="right"
          domain={[-1, 1]}
          tick={{ fontSize: 12, fill: TICK }}
          stroke={GRID}
        />
        <Tooltip
          contentStyle={{ fontSize: 12, borderRadius: 8, border: `1px solid ${GRID}` }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {/* 감정 중립선 */}
        <ReferenceLine yAxisId="sent" y={0} stroke={GRID} strokeDasharray="2 2" />
        <Line
          yAxisId="price"
          type="monotone"
          dataKey="close"
          name="종가"
          stroke={PRICE}
          strokeWidth={2}
          dot={false}
        />
        <Line
          yAxisId="sent"
          type="monotone"
          dataKey="avg_sentiment"
          name="평균 감정"
          stroke={SENT}
          strokeWidth={2}
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
