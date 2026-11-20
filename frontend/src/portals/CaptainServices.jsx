import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api'

const DAYS = [
  ['0', 'الاثنين', 'Monday', 'יום שני'],
  ['1', 'الثلاثاء', 'Tuesday', 'יום שלישי'],
  ['2', 'الأربعاء', 'Wednesday', 'יום רביעי'],
  ['3', 'الخميس', 'Thursday', 'יום חמישי'],
  ['4', 'الجمعة', 'Friday', 'יום שישי'],
  ['5', 'السبت', 'Saturday', 'שבת'],
  ['6', 'الأحد', 'Sunday', 'יום ראשון'],
]
const dayLabel = (lang, value) => {
  const row = DAYS.find(item => item[0] === String(value)) || DAYS[0]
  return lang === 'en' ? row[2] : lang === 'he' ? row[3] : row[1]
}
const SERVICE_ICON = {
  food: '🍽', grocery: '🛒', pharmacy: '✚', parcel: '📦', ride: '🛵', logistics: '🚚',
}

export function CaptainServicesPanel({ t, profile, onChanged }) {
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const services = profile?.service_options || []
  const approved = services.filter(row => row.status === 'approved')

  async function toggle(row) {
    if (row.status !== 'approved' || busy) return
    setBusy(row.service)
    setError('')
    try {
      await api('/captains/me/services/', {
        method: 'POST',
        body: JSON.stringify({ services: [{ service: row.service, accepting: !row.accepting }] }),
      })
      await onChanged?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  return <section className="panel">
    <div className="section-head"><div><h3>{t.captainServices}</h3><p>{t.captainServicesHint}</p></div>
      <span className="tag">{approved.length}/{services.length}</span></div>
    {error && <p className="error">{error}</p>}
    <div className="service-grid">
      {services.map(row => <button
        type="button"
        key={row.service}
        className={`service-card ${row.status === 'approved' ? 'is-approved' : row.status === 'suspended' ? 'is-suspended' : 'is-locked'} ${row.accepting ? 'is-accepting' : ''}`}
        disabled={row.status !== 'approved' || busy === row.service}
        onClick={() => toggle(row)}
        aria-pressed={!!row.accepting}
      >
        <span className="service-card-icon" aria-hidden="true">{SERVICE_ICON[row.service] || '•'}</span>
        <strong>{t[`service_${row.service}`] || row.label}</strong>
        <small>{row.status === 'none' ? t.serviceNotRequested : row.status === 'approved' ? (row.accepting ? t.serviceAccepting : t.servicePaused) : row.status === 'suspended' ? t.serviceSuspended : t.servicePendingApproval}</small>
      </button>)}
    </div>
    {!services.length && <p className="note">{t.noServicesConfigured}</p>}
    <p className="note">{t.captainServicesNote}</p>
  </section>
}

export function CaptainSchedulePanel({ t, lang }) {
  const [windows, setWindows] = useState([])
  const [meta, setMeta] = useState({ available_now: false, uses_default_schedule: true })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function load() {
    try {
      const data = await api('/captains/me/schedule/')
      setWindows((data.windows || []).map(row => ({
        weekday: String(row.weekday), start_time: row.start_time.slice(0, 5),
        end_time: row.end_time.slice(0, 5), is_break: !!row.is_break,
      })))
      setMeta({ available_now: data.available_now, uses_default_schedule: data.uses_default_schedule })
      setError('')
    } catch (e) { setError(e.message) }
  }
  useEffect(() => { load() }, [])

  function update(index, key, value) {
    setWindows(rows => rows.map((row, i) => i === index ? { ...row, [key]: value } : row))
  }
  function addRow(isBreak) {
    setWindows(rows => [...rows, { weekday: '0', start_time: '08:00', end_time: isBreak ? '09:00' : '17:00', is_break: isBreak }])
  }
  async function save() {
    setBusy(true); setError(''); setNotice('')
    try {
      const payload = windows.map(row => ({
        weekday: Number(row.weekday), start_time: row.start_time,
        end_time: row.end_time, is_break: !!row.is_break,
      }))
      const data = await api('/captains/me/schedule/', { method: 'PUT', body: JSON.stringify({ windows: payload }) })
      setMeta({ available_now: data.available_now, uses_default_schedule: data.uses_default_schedule })
      setNotice(t.scheduleSaved)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  async function clearAll() {
    setBusy(true); setError(''); setNotice('')
    try {
      const data = await api('/captains/me/schedule/', { method: 'PUT', body: JSON.stringify({ windows: [] }) })
      setWindows([])
      setMeta({ available_now: data.available_now, uses_default_schedule: data.uses_default_schedule })
      setNotice(t.scheduleCleared)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  return <section className="panel">
    <div className="section-head"><div><h3>{t.workingSchedule}</h3><p>{t.workingScheduleHint}</p></div>
      <span className={`status-pill ${meta.available_now ? '' : 'is-offline'}`}>{meta.available_now ? t.availableNow : t.outsideHours}</span></div>
    {meta.uses_default_schedule && <p className="note">{t.defaultScheduleNote}</p>}
    {windows.map((row, index) => <div className="schedule-row" key={index}>
      <select value={row.weekday} onChange={e => update(index, 'weekday', e.target.value)} aria-label={t.weekday}>
        {DAYS.map(day => <option key={day[0]} value={day[0]}>{dayLabel(lang, day[0])}</option>)}
      </select>
      <input type="time" value={row.start_time} onChange={e => update(index, 'start_time', e.target.value)} aria-label={t.from}/>
      <input type="time" value={row.end_time} onChange={e => update(index, 'end_time', e.target.value)} aria-label={t.to}/>
      <label className="check-label"><input type="checkbox" checked={row.is_break} onChange={e => update(index, 'is_break', e.target.checked)}/>{t.breakWindow}</label>
      <button type="button" className="secondary danger" onClick={() => setWindows(rows => rows.filter((_, i) => i !== index))}>{t.remove}</button>
    </div>)}
    {!windows.length && <p className="note">{t.noScheduleWindows}</p>}
    {error && <p className="error">{error}</p>}
    {notice && <p className="success-note">{notice}</p>}
    <div className="row-actions">
      <button type="button" className="secondary" onClick={() => addRow(false)}>{t.addWorkingWindow}</button>
      <button type="button" className="secondary" onClick={() => addRow(true)}>{t.addBreakWindow}</button>
      <button type="button" disabled={busy} onClick={save}>{busy ? t.saving : t.saveSchedule}</button>
      <button type="button" className="secondary" disabled={busy || !windows.length} onClick={clearAll}>{t.clearSchedule}</button>
    </div>
  </section>
}

export function CaptainEarningsPanel({ t, lang }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let live = true
    api('/captains/me/earnings/').then(rows => { if (live) { setData(rows); setError('') } }).catch(e => live && setError(e.message))
    return () => { live = false }
  }, [])
  const money = value => `${Number(value || 0).toFixed(2)} ₪`
  const cards = useMemo(() => data ? [
    [t.earningsToday, data.today?.amount, data.today?.tasks],
    [t.earningsWeek, data.week?.amount, data.week?.tasks],
    [t.earningsMonth, data.month?.amount, data.month?.tasks],
    [t.cashCollected, data.cash_collected, null],
  ] : [], [data, t])
  if (!data && !error) return <section className="panel"><div className="stats">{[0, 1, 2, 3].map(i => <div className="stat skeleton" key={i}/>)}</div></section>
  return <section className="panel">
    <div className="section-head"><div><h3>{t.earningsAndSettlements}</h3><p>{t.earningsHint}</p></div>
      <button type="button" className="secondary" onClick={() => window.print()}>{t.printStatement}</button></div>
    {error && <p className="error">{error}</p>}
    {data && <>
      <div className="stats">{cards.map(([label, value, tasks]) => <article className="stat" key={label}>
        <div className="stat-head"><small>{label}</small></div><strong>{money(value)}</strong>{tasks != null && <small>{tasks} {t.tasksCompleted}</small>}
      </article>)}</div>
      <div className="stats captain-summary">
        <article className="stat"><div className="stat-head"><small>{t.completedTasks}</small></div><strong>{data.completed_tasks}</strong></article>
        <article className="stat"><div className="stat-head"><small>{t.averageCompletion}</small></div><strong>{data.average_completion_minutes != null ? `${data.average_completion_minutes} ${t.minutesShort}` : '—'}</strong></article>
        <article className="stat"><div className="stat-head"><small>{t.outstandingAmount}</small></div><strong>{money(data.outstanding_total)}</strong></article>
      </div>
      <p className="note">{data.note || t.earningsPolicyNote}</p>
      <h3>{t.settlementHistory}</h3>
      <div className="table-wrap"><table><thead><tr><th>{t.orderPrefix}</th><th>{t.merchantName}</th><th>{t.productsAmount}</th><th>{t.productsSettled}</th><th>{t.outstandingAmount}</th><th>{t.status}</th></tr></thead>
        <tbody>{(data.settlements || []).map(row => <tr key={row.id}><td>{row.order_number}</td><td>{row.merchant_name}</td><td>{money(row.amount)}</td><td>{money(row.settled_amount)}</td><td>{money(row.outstanding_amount)}</td><td>{t[row.status] || row.status}</td></tr>)}
          {!(data.settlements || []).length && <tr><td colSpan="6">{t.noSettlements}</td></tr>}</tbody></table></div>
      <h3>{t.completedTaskDetails}</h3>
      <div className="table-wrap"><table><thead><tr><th>{t.orderPrefix}</th><th>{t.serviceType}</th><th>{t.merchantName}</th><th>{t.deliveryFee}</th><th>{t.date}</th></tr></thead>
        <tbody>{(data.tasks || []).map((row, index) => <tr key={`${row.order_number}-${index}`}><td>{row.order_number}</td><td>{t[`service_${row.service_type}`] || row.service_type}</td><td>{row.merchant_name || '—'}</td><td>{money(row.delivery_fee)}</td><td dir="ltr">{row.completed_at ? new Date(row.completed_at).toLocaleDateString(lang === 'en' ? 'en' : 'ar') : '—'}</td></tr>)}
          {!(data.tasks || []).length && <tr><td colSpan="5">{t.noCompletedTasks}</td></tr>}</tbody></table></div>
    </>}
  </section>
}
