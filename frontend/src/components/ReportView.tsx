import ReactMarkdown from 'react-markdown'
import type { Report } from '../api/client'
import { LoadState } from './LoadState'
import type { Status } from './LoadState'
import { formatKoDate } from '../lib/date'

export function ReportView({
  report,
  status,
  onRetry,
}: {
  report: Report | null
  status: Status
  onRetry?: () => void
}) {
  if (status !== 'ready') {
    return (
      <LoadState status={status} rows={6} onRetry={onRetry} label="리포트를 불러오지 못했습니다." />
    )
  }
  if (!report) {
    return <p className="empty">아직 만들어진 리포트가 없어요.</p>
  }
  return (
    <article className="report">
      <div className="report-meta">
        <span className="report-date">{formatKoDate(report.date)} 브리핑</span>
        {report.model && <span className="report-model mono">{report.model}</span>}
      </div>
      <ReactMarkdown>{report.body_md}</ReactMarkdown>
    </article>
  )
}
