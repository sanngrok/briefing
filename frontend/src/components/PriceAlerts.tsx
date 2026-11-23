import { useState } from 'react'
import {
  NEAR_PCT,
  formatAlertPrice,
  setAlert,
  toSecretLine,
  validateAlertInput,
} from '../lib/alerts'
import type { AlertKind, AlertRow, Alerts } from '../lib/alerts'
import { StockAvatar } from './StockAvatar'

export type NotifyPermission = NotificationPermission | 'unsupported'

const STATUS: Record<AlertKind, { label: string; cls: string }> = {
  'target-hit': { label: '목표가 도달', cls: 'st-up' },
  'stop-hit': { label: '손절가 도달', cls: 'st-down' },
  'near-target': { label: '목표가 근접', cls: 'st-up-soft' },
  'near-stop': { label: '손절가 근접', cls: 'st-down-soft' },
  watching: { label: '지켜보는 중', cls: 'st-flat' },
}

function pct(n: number): string {
  return `${Math.abs(n).toFixed(1)}%`
}

/** 손절가 ── ● ── 목표가 막대, 또는 한쪽만 있을 때 남은 거리 한 줄 */
function Progress({ row }: { row: AlertRow }) {
  const { setting, status, currency } = row
  if (!setting) return null
  if (!status) {
    return <p className="al-distance">현재가를 몰라 판정을 쉬고 있어요.</p>
  }
  if (status.position !== null && setting.stop != null && setting.target != null) {
    return (
      <div className="al-track-wrap">
        <div className="al-track" aria-hidden="true">
          <div className="al-track-fill" style={{ width: `${status.position * 100}%` }} />
          <div className="al-track-dot" style={{ left: `${status.position * 100}%` }} />
        </div>
        <div className="al-track-labels mono">
          <span className="dir-down">손절 {formatAlertPrice(setting.stop, currency)}</span>
          <span className="dir-up">목표 {formatAlertPrice(setting.target, currency)}</span>
        </div>
      </div>
    )
  }
  return (
    <p className="al-distance mono">
      {setting.target != null && status.toTarget !== null && (
        <span>
          목표 {formatAlertPrice(setting.target, currency)}
          {status.toTarget > 0 ? `까지 +${pct(status.toTarget)}` : ' 넘음'}
        </span>
      )}
      {setting.stop != null && status.toStop !== null && (
        <span>
          손절 {formatAlertPrice(setting.stop, currency)}
          {status.toStop > 0 ? `까지 −${pct(status.toStop)}` : ' 깨짐'}
        </span>
      )}
    </p>
  )
}

function Editor({
  row,
  onSave,
  onCancel,
}: {
  row: AlertRow
  onSave: (setting: ReturnType<typeof validateAlertInput>) => void
  onCancel: () => void
}) {
  const unit = row.currency === 'USD' ? '달러' : '원'
  const [target, setTarget] = useState(row.setting?.target?.toString() ?? '')
  const [stop, setStop] = useState(row.setting?.stop?.toString() ?? '')
  // 빈칸에는 현재가 ±10% 를 예시로 보여 준다(값을 대신 넣지는 않는다).
  const hint = (k: number) =>
    row.price != null
      ? row.currency === 'USD'
        ? (row.price * k).toFixed(2)
        : String(Math.round((row.price * k) / 100) * 100)
      : ''

  return (
    <form
      className="al-editor"
      onSubmit={(e) => {
        e.preventDefault()
        onSave(validateAlertInput(target, stop))
      }}
    >
      <div className="pf-field">
        <label htmlFor={`al-stop-${row.symbol}`}>손절가 ({unit})</label>
        <input
          id={`al-stop-${row.symbol}`}
          inputMode="decimal"
          placeholder={hint(0.9)}
          value={stop}
          onChange={(e) => setStop(e.target.value)}
        />
      </div>
      <div className="pf-field">
        <label htmlFor={`al-target-${row.symbol}`}>목표가 ({unit})</label>
        <input
          id={`al-target-${row.symbol}`}
          inputMode="decimal"
          placeholder={hint(1.1)}
          value={target}
          onChange={(e) => setTarget(e.target.value)}
        />
      </div>
      <div className="pf-actions">
        <button type="submit" className="pf-btn pf-btn-primary">
          저장
        </button>
        <button type="button" className="pf-btn" onClick={onCancel}>
          취소
        </button>
      </div>
    </form>
  )
}

/**
 * 목표가 · 손절가. 내 자산 화면에서 보유 종목마다 걸고, 도달·근접을 보여 준다.
 * 판정(rows)은 App 이 한다 — 메뉴 배지와 브라우저 알림도 같은 결과를 쓰기 때문이다.
 */
export function PriceAlerts({
  rows,
  alerts,
  onChange,
  notifyPermission,
  onEnableNotify,
}: {
  rows: AlertRow[]
  alerts: Alerts
  onChange: (next: Alerts) => void
  notifyPermission: NotifyPermission
  onEnableNotify: () => void
}) {
  const [editing, setEditing] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const configured = rows.filter((r) => r.setting)
  const hits = rows.filter((r) => r.status && r.status.kind.endsWith('-hit'))

  function flash(msg: string) {
    setNotice(msg)
    setError('')
    window.setTimeout(() => setNotice(''), 6000)
  }

  async function copySecret() {
    const line = toSecretLine(
      rows.map((r) => r.symbol),
      alerts,
    )
    try {
      await navigator.clipboard.writeText(line)
      flash('복사했어요. GitHub 시크릿 HOLDING_SYMBOLS 를 이 값으로 바꾸면 아침 메일에도 알려 드려요.')
    } catch {
      // 클립보드 권한이 없으면 값을 직접 보여 준다
      window.prompt('아래 값을 복사해 GitHub 시크릿 HOLDING_SYMBOLS 에 넣어 주세요.', line)
    }
  }

  return (
    <section className="panel pf-alerts" aria-label="목표가 · 손절가">
      <div className="pf-head">
        <h2 className="pf-head-title">
          목표가 · 손절가
          {configured.length > 0 && <span className="pf-count mono">{configured.length}</span>}
        </h2>
        <div className="al-head-btns">
          {notifyPermission === 'default' && (
            <button type="button" className="pf-btn pf-btn-sm" onClick={onEnableNotify}>
              브라우저 알림 켜기
            </button>
          )}
          {notifyPermission === 'granted' && <span className="al-chip">브라우저 알림 켜짐</span>}
          {configured.length > 0 && (
            <button type="button" className="pf-btn pf-btn-sm" onClick={copySecret}>
              메일 알림 설정 복사
            </button>
          )}
        </div>
      </div>

      <p className="al-desc">
        도달하면 위에 바로 표시하고, {NEAR_PCT}% 안으로 다가오면 '근접'으로 알려 드려요. 해외
        종목은 달러 기준이에요.
        {notifyPermission === 'denied' &&
          ' 브라우저 알림은 차단돼 있어요(주소창 왼쪽 자물쇠에서 바꿀 수 있어요).'}
      </p>

      {hits.length > 0 && (
        <div className="al-banner" role="status">
          {hits.map((r) => (
            <span key={r.symbol} className={r.status!.kind === 'target-hit' ? 'dir-up' : 'dir-down'}>
              {r.name}{' '}
              {STATUS[r.status!.kind].label}
            </span>
          ))}
        </div>
      )}

      {error && <p className="pf-error">{error}</p>}
      {notice && <p className="pf-notice">{notice}</p>}

      <ul className="al-list">
        {rows.map((r) => {
          const st = r.status ? STATUS[r.status.kind] : null
          const isEditing = editing === r.symbol
          return (
            <li key={r.symbol} className={`al-row${r.setting ? '' : ' al-row-off'}`}>
              <div className="al-top">
                <StockAvatar name={r.name} />
                <div className="al-main">
                  <span className="al-name">{r.name}</span>
                  <span className="al-price mono">
                    {formatAlertPrice(r.price, r.currency)}
                    {r.stale && <span className="al-stale"> · 가져온 시세</span>}
                  </span>
                </div>
                {st && <span className={`al-status ${st.cls}`}>{st.label}</span>}
                {!isEditing && (
                  <button
                    type="button"
                    className={`pf-btn pf-btn-sm${r.setting ? '' : ' pf-btn-weak'}`}
                    onClick={() => {
                      setEditing(r.symbol)
                      setError('')
                    }}
                  >
                    {r.setting ? '수정' : '+ 설정'}
                  </button>
                )}
              </div>

              {!isEditing && <Progress row={r} />}

              {isEditing && (
                <>
                  <Editor
                    row={r}
                    onCancel={() => setEditing(null)}
                    onSave={(res) => {
                      if (!res.ok) {
                        setError(res.error)
                        return
                      }
                      onChange(setAlert(alerts, r.symbol, res.setting))
                      setEditing(null)
                      flash(res.setting ? `${r.name} 알림을 저장했어요.` : `${r.name} 알림을 껐어요.`)
                    }}
                  />
                  {r.setting && (
                    <button
                      type="button"
                      className="al-clear"
                      onClick={() => {
                        onChange(setAlert(alerts, r.symbol, null))
                        setEditing(null)
                        flash(`${r.name} 알림을 껐어요.`)
                      }}
                    >
                      알림 끄기
                    </button>
                  )}
                </>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
