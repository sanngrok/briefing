/**
 * API 호출 하나의 상태. 'ready' 안에서도 결과가 빌 수 있고, 그 구분이 핵심이다.
 *
 * 셋을 갈라 두지 않으면 아직 안 온 것 · 못 받은 것 · 진짜 없는 것이 모두 같은
 * "데이터 없음" 문구로 보인다. Render 무료 티어는 15분 미사용 뒤 첫 요청이
 * 30~60초 걸리는데(README 배포 절), 그 사이 화면이 "표시할 뉴스가 없습니다"만
 * 띄워서 파이프라인이 망가진 것처럼 읽혔다.
 */
export type Status = 'loading' | 'error' | 'ready'

/**
 * 로딩 중 자리를 지키는 회색 막대. 실제 내용과 비슷한 높이로 잡아 데이터가
 * 도착할 때 레이아웃이 튀지 않게 한다.
 */
function Skeleton({ rows }: { rows: number }) {
  return (
    <div className="skel" aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skel-bar" />
      ))}
    </div>
  )
}

/**
 * 아직 준비되지 않은 데이터 자리에 놓는다. 'ready' 는 각 화면이 직접 처리한다 —
 * 비었을 때의 문구가 섹션마다 다르기 때문이다.
 */
export function LoadState({
  status,
  rows = 3,
  onRetry,
  label = '데이터를 불러오지 못했습니다.',
}: {
  status: Exclude<Status, 'ready'>
  rows?: number
  onRetry?: () => void
  label?: string
}) {
  if (status === 'loading') {
    return (
      <div className="loading" role="status" aria-live="polite">
        <Skeleton rows={rows} />
        <span className="loading-note">불러오는 중…</span>
      </div>
    )
  }

  return (
    <div className="loadfail" role="alert">
      <p className="loadfail-msg">{label}</p>
      <p className="loadfail-hint">
        서버가 절전 상태에서 깨어나는 중이면 30~60초 뒤에 다시 시도하면 됩니다.
      </p>
      {onRetry && (
        <button type="button" className="loadfail-btn" onClick={onRetry}>
          다시 시도
        </button>
      )}
    </div>
  )
}
