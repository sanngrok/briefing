// API 클라이언트 + 응답 타입 (백엔드 Pydantic 모델과 계약 일치)

export type Severity = 'low' | 'mid' | 'high'

export interface Report {
  date: string
  scope: string
  body_md: string
  model?: string | null
  created_at?: string | null
}

export interface MetricPoint {
  date: string
  close?: number | null
  change_pct?: number | null
  volume?: number | null
  avg_sentiment?: number | null
  news_count?: number | null
}

export interface TickerMetrics {
  symbol: string
  name: string
  series: MetricPoint[]
}

export interface Signal {
  date: string
  symbol?: string | null
  name?: string | null
  type: string
  severity: Severity
  evidence: Record<string, unknown>
}

const BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return (await res.json()) as T
}

export const api = {
  latestReport: () => get<Report>('/api/reports/latest'),

  signals: (params?: { date?: string; severity?: Severity }) => {
    const q = new URLSearchParams()
    if (params?.date) q.set('date', params.date)
    if (params?.severity) q.set('severity', params.severity)
    const qs = q.toString()
    return get<Signal[]>(`/api/signals${qs ? `?${qs}` : ''}`)
  },

  metrics: (symbol: string, range?: { from?: string; to?: string }) => {
    const q = new URLSearchParams()
    if (range?.from) q.set('from', range.from)
    if (range?.to) q.set('to', range.to)
    const qs = q.toString()
    return get<TickerMetrics>(`/api/tickers/${symbol}/metrics${qs ? `?${qs}` : ''}`)
  },
}
