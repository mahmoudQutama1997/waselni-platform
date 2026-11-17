import { useEffect, useState } from 'react'
import Icon from './Icons.jsx'

/** Placeholder block used while real data is loading. */
export function Skeleton({ height = 16, width = '100%', radius = undefined, style = undefined }) {
  return <span className="ds-skeleton" style={{ display: 'block', height, width, borderRadius: radius, ...style }} />
}

export function SkeletonCards({ count = 4 }) {
  return (
    <div className="ds-skeleton-grid">
      {Array.from({ length: count }).map((_, index) => (
        <div className="ds-skeleton ds-skeleton-card" key={index} />
      ))}
    </div>
  )
}

export function SkeletonLines({ count = 3 }) {
  return (
    <div>
      {Array.from({ length: count }).map((_, index) => (
        <span
          key={index}
          className="ds-skeleton ds-skeleton-line"
          style={{ display: 'block', width: `${100 - index * 12}%` }}
        />
      ))}
    </div>
  )
}

/** Professional empty state with an icon, title and explanation. */
export function EmptyState({ icon = 'package', title = '', description = '', action = null }) {
  return (
    <div className="ds-empty">
      <span className="ds-empty-icon"><Icon name={icon} size={24} /></span>
      {title && <b>{title}</b>}
      {description && <p>{description}</p>}
      {action}
    </div>
  )
}

export function SectionHead({ eyebrow = '', title = '', description = '', action = null }) {
  return (
    <div className="ds-section-head">
      <div>
        {eyebrow && <span className="ds-eyebrow">{eyebrow}</span>}
        <h2>{title}</h2>
        {description && <p>{description}</p>}
      </div>
      {action}
    </div>
  )
}

const STATUS_TONES = {
  new: 'info',
  accepted: 'info',
  preparing: 'warning',
  ready: 'warning',
  assigned: 'info',
  picked_up: 'info',
  delivering: 'info',
  completed: 'success',
  cancelled: 'danger',
  open: 'warning',
  in_review: 'info',
  resolved: 'success',
}

/** Status pill driven by the real order/ticket status values. */
export function StatusBadge({ status = '', label = '', className = '' }) {
  const tone = STATUS_TONES[status] || 'neutral'
  return <span className={`ds-badge ds-badge--${tone} ${className}`}>{label || status}</span>
}

export function StatCard({ label = '', value = '', sub = '', icon = 'trending' }) {
  return (
    <article className="ds-stat">
      <span className="ds-stat-label"><Icon name={icon} size={14} />{label}</span>
      <strong className="ds-stat-value">{value}</strong>
      {sub && <small className="ds-stat-sub">{sub}</small>}
    </article>
  )
}

/**
 * Pure-SVG/HTML bar chart. Renders only the values it is given, so it never
 * invents data: callers pass real aggregates from the API.
 */
export function BarChart({ data = [], valueFormatter = (value) => value, emptyLabel = '' }) {
  const max = Math.max(...data.map((row) => Number(row.value) || 0), 0)
  if (!data.length || max <= 0) {
    return <p className="ds-empty" style={{ padding: '18px' }}>{emptyLabel || '—'}</p>
  }
  return (
    <div className="ds-chart">
      <div className="ds-chart-bars" role="img" aria-label={data.map((row) => `${row.label}: ${valueFormatter(row.value)}`).join(', ')}>
        {data.map((row) => {
          const value = Number(row.value) || 0
          const height = Math.max(3, Math.round((value / max) * 100))
          return (
            <div className="ds-chart-col" key={row.label} title={`${row.label}: ${valueFormatter(value)}`}>
              <span className={`ds-chart-bar ${row.muted ? 'ds-chart-bar--muted' : ''}`} style={{ height: `${height}%` }} />
            </div>
          )
        })}
      </div>
      <div className="ds-chart-labels">
        {data.map((row) => <span key={row.label}>{row.label}</span>)}
      </div>
    </div>
  )
}

/** Compact distribution list with progress bars, for status/type breakdowns. */
export function DistributionList({ rows = [], total = 0, labelFormatter = (label) => label }) {
  if (!rows.length || !total) {
    return <p className="ds-empty" style={{ padding: '18px' }}>—</p>
  }
  return (
    <div style={{ display: 'grid', gap: '11px' }}>
      {rows.map((row) => {
        const percent = Math.round((row.value / total) * 100)
        return (
          <div key={row.label} style={{ display: 'grid', gap: '5px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: 'var(--w-muted)' }}>
              <span>{labelFormatter(row.label)}</span>
              <b style={{ color: 'var(--w-ink)' }}>{row.value} · {percent}%</b>
            </div>
            <div className="ds-progress"><i style={{ width: `${percent}%` }} /></div>
          </div>
        )
      })}
    </div>
  )
}

/** Opt-in dark mode. Light remains the default. */
export function ThemeToggle({ labelLight = 'الوضع الليلي', labelDark = 'الوضع النهاري' }) {
  const [theme, setTheme] = useState(() => localStorage.getItem('waselni_theme') || 'light')
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('waselni_theme', theme)
  }, [theme])
  const dark = theme === 'dark'
  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={() => setTheme(dark ? 'light' : 'dark')}
      aria-pressed={dark}
      title={dark ? labelDark : labelLight}
    >
      <Icon name={dark ? 'sun' : 'moon'} size={15} />
      <span>{dark ? labelDark : labelLight}</span>
    </button>
  )
}

/** Freshness label for GPS positions so stale points are never called live. */
export function freshness(isoValue, staleAfterMs = 90000) {
  if (!isoValue) return { fresh: false, label: null }
  const timestamp = new Date(isoValue).getTime()
  if (!Number.isFinite(timestamp)) return { fresh: false, label: null }
  const age = Date.now() - timestamp
  return {
    fresh: age >= 0 && age < staleAfterMs,
    age,
    label: new Date(timestamp).toLocaleTimeString(),
  }
}

export function ErrorNotice({ message = '' }) {
  if (!message) return null
  return (
    <div className="ds-alert ds-alert--error" role="alert">
      <Icon name="alert" size={16} />
      <span>{message}</span>
    </div>
  )
}
