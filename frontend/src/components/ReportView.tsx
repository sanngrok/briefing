import ReactMarkdown from 'react-markdown'
import type { Report } from '../api/client'
import { LoadState } from './LoadState'
import type { Status } from './LoadState'

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
    return <p className="empty">아직 생성된 리포트가 없습니다.</p>
  }
  return (
    <article className="report">
      <div className="report-meta">
        {report.date}
        {report.model ? ` · ${report.model}` : ''}
      </div>
      <ReactMarkdown>{report.body_md}</ReactMarkdown>
    </article>
  )
}
