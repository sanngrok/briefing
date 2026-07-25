import ReactMarkdown from 'react-markdown'
import type { Report } from '../api/client'

export function ReportView({ report }: { report: Report | null }) {
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
