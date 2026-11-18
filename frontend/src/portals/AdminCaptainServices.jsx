import React, { useEffect, useState } from 'react'
import { api } from '../api'

const LABEL = {
  food: 'توصيل المطاعم', grocery: 'سوبرماركت', pharmacy: 'صيدليات',
  parcel: 'طرود ومستندات', ride: 'مشاوير فسبا', logistics: 'لوجستيات',
}

export default function AdminCaptainServices({ t, onError }) {
  const [captains, setCaptains] = useState([])
  const [selected, setSelected] = useState('')
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [limit, setLimit] = useState('1')

  async function loadCaptains() {
    try {
      const payload = await api('/admin/operations/')
      setCaptains(payload.captains || [])
      if (!selected && payload.captains?.length) setSelected(String(payload.captains[0].captain_profile_id))
    } catch (e) { setError(e.message); onError?.(e.message) }
  }
  async function loadServices(id) {
    if (!id) return
    try {
      const payload = await api(`/admin/captains/${id}/services/`)
      setData(payload)
      setLimit(String(payload.max_active_tasks || 1))
      setError('')
    } catch (e) { setError(e.message) }
  }
  useEffect(() => { loadCaptains() }, [])
  useEffect(() => { loadServices(selected) }, [selected])

  async function setStatus(service, status) {
    setBusy(`${service}-${status}`)
    try {
      await api(`/admin/captains/${selected}/services/`, {
        method: 'POST', body: JSON.stringify({ service, status }),
      })
      await loadServices(selected)
      await loadCaptains()
    } catch (e) { setError(e.message) } finally { setBusy('') }
  }
  async function saveLimit() {
    const food = data?.services?.find(row => row.service === 'food')
    setBusy('limit')
    try {
      await api(`/admin/captains/${selected}/services/`, {
        method: 'POST',
        body: JSON.stringify({ service: 'food', status: food?.status === 'none' ? 'pending' : food.status, max_active_tasks: Number(limit) }),
      })
      await loadServices(selected)
    } catch (e) { setError(e.message) } finally { setBusy('') }
  }

  return <section className="panel">
    <div className="section-head"><div><h3>{t.captainServicesAdmin}</h3><p>{t.captainServicesAdminHint}</p></div>
      <select value={selected} onChange={e => setSelected(e.target.value)} aria-label={t.captainName}>
        {captains.map(row => <option key={row.captain_profile_id} value={row.captain_profile_id}>{row.name} · {row.username}</option>)}
      </select></div>
    {error && <p className="error">{error}</p>}
    {!data && <p className="note">{t.empty}</p>}
    {data && <>
      <div className="table-wrap"><table><thead><tr><th>{t.serviceType}</th><th>{t.status}</th><th>{t.regions}</th><th>{t.actions}</th></tr></thead>
        <tbody>{data.services.map(row => <tr key={row.service}>
          <td>{LABEL[row.service] || row.service}</td>
          <td><span className={`tag ${row.status}`}>{t[`approval_${row.status}`] || row.status}</span></td>
          <td>{row.regions?.length ? row.regions.join(' · ') : '—'}</td>
          <td className="row-actions">
            <button type="button" className="secondary" disabled={busy === `${row.service}-approved`}
              onClick={() => setStatus(row.service, 'approved')}>{t.approveService}</button>
            <button type="button" className="secondary danger" disabled={busy === `${row.service}-suspended`}
              onClick={() => setStatus(row.service, 'suspended')}>{t.suspendService}</button>
          </td></tr>)}</tbody></table></div>
      <div className="row-actions"><label>{t.maxActiveTasks}
        <input type="number" min="1" max="10" value={limit} onChange={e => setLimit(e.target.value)} style={{ maxWidth: 90 }}/>
      </label><button type="button" className="secondary" disabled={busy === 'limit'} onClick={saveLimit}>{t.save}</button></div>
    </>}
  </section>
}
