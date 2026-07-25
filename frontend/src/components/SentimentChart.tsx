import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import type { MetricPoint } from '../api/client'

export function SentimentChart({ data }: { data: MetricPoint[] }) {
  if (data.length === 0) {
    return <p className="empty">표시할 시세 데이터가 없습니다.</p>
  }
  return (
    <ResponsiveContainer width="100%" height={320}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
        <XAxis dataKey="date" tick={{ fontSize: 12 }} />
        <YAxis yAxisId="price" tick={{ fontSize: 12 }} />
        <YAxis
          yAxisId="sent"
          orientation="right"
          domain={[-1, 1]}
          tick={{ fontSize: 12 }}
        />
        <Tooltip />
        <Legend />
        <Line
          yAxisId="price"
          type="monotone"
          dataKey="close"
          name="종가"
          stroke="#2563eb"
          dot={false}
        />
        <Line
          yAxisId="sent"
          type="monotone"
          dataKey="avg_sentiment"
          name="평균 감정"
          stroke="#16a34a"
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
