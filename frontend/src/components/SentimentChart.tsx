import {
  ComposedChart,
  Area,
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
import { LoadState } from './LoadState'
import type { Status } from './LoadState'

// SVG 속성은 CSS 변수를 못 받으므로 index.css 팔레트와 같은 값을 고정으로 둔다.
const GRID = '#f2f4f6' // --panel-3
const TICK = '#8b95a1' // --muted
const PRICE = '#3182f6' // --accent (토스 블루)
const SENT = '#fe9800' // TDS orange500 — 파랑과 겹치지 않는 따뜻한 색

export function SentimentChart({
  data,
  status,
  onRetry,
}: {
  data: MetricPoint[]
  status: Status
  onRetry?: () => void
}) {
  if (status !== 'ready') {
    return (
      <LoadState status={status} rows={5} onRetry={onRetry} label="종목 추이를 불러오지 못했습니다." />
    )
  }
  if (data.length === 0) {
    return <p className="empty">표시할 시세 데이터가 없어요.</p>
  }
  return (
    <ResponsiveContainer width="100%" height={320}>
      <ComposedChart data={data} margin={{ top: 12, right: 4, bottom: 4, left: -8 }}>
        <defs>
          {/* 종가 아래를 옅은 파랑으로 채워 선 하나보다 부드럽게 보이게 한다 */}
          <linearGradient id="price-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={PRICE} stopOpacity={0.18} />
            <stop offset="100%" stopColor={PRICE} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 12, fill: TICK }}
          axisLine={false}
          tickLine={false}
          tickMargin={10}
          minTickGap={24}
        />
        <YAxis
          yAxisId="price"
          tick={{ fontSize: 12, fill: TICK }}
          axisLine={false}
          tickLine={false}
          width={64}
          domain={['auto', 'auto']}
          tickFormatter={(v: number) => v.toLocaleString('ko-KR')}
        />
        <YAxis
          yAxisId="sent"
          orientation="right"
          domain={[-1, 1]}
          tick={{ fontSize: 12, fill: TICK }}
          axisLine={false}
          tickLine={false}
          width={36}
        />
        <Tooltip
          cursor={{ stroke: '#d1d6db', strokeDasharray: '3 3' }}
          contentStyle={{
            fontSize: 13,
            borderRadius: 14,
            border: 'none',
            padding: '10px 14px',
            boxShadow: '0 8px 24px rgba(0, 29, 58, 0.12)',
          }}
          labelStyle={{ color: TICK, marginBottom: 4 }}
        />
        <Legend
          iconType="circle"
          iconSize={8}
          wrapperStyle={{ fontSize: 13, paddingTop: 8 }}
        />
        {/* 감정 중립선 */}
        <ReferenceLine yAxisId="sent" y={0} stroke="#e5e8eb" strokeDasharray="4 4" />
        <Area
          yAxisId="price"
          type="monotone"
          dataKey="close"
          name="종가"
          stroke={PRICE}
          strokeWidth={2.5}
          fill="url(#price-fill)"
          dot={false}
          activeDot={{ r: 5, strokeWidth: 3, stroke: '#fff' }}
          // 주말·휴장일은 종가가 비어 있다(그날 뉴스만 있다). 장이 안 열린 날은 직전
          // 종가가 이어지는 것이므로 잇는다. 감정선은 기사가 없던 날을 비워 둔다.
          connectNulls
        />
        <Line
          yAxisId="sent"
          type="monotone"
          dataKey="avg_sentiment"
          name="평균 감정"
          stroke={SENT}
          strokeWidth={2.5}
          dot={false}
          activeDot={{ r: 5, strokeWidth: 3, stroke: '#fff' }}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
