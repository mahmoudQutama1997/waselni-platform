import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api'

const money = value => `${Number(value || 0).toFixed(2)} ₪`
const DAYS = ['الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت', 'الأحد']
const ROLE_LABEL = {
  owner: 'المالك', manager: 'مدير', orders: 'موظف طلبات', preparation: 'موظف تجهيز',
  inventory: 'مسؤول مخزون', reports: 'موظف تقارير',
}

export default function MerchantOperations({ t, lang }) {
  const [dashboard, setDashboard] = useState(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState('overview')
  const [notice, setNotice] = useState('')

  async function loadDashboard() {
    try { setDashboard(await api('/merchant/dashboard/')); setError('') }
    catch (e) { setError(e.message) }
  }
  useEffect(() => { loadDashboard(); const id = setInterval(loadDashboard, 15000); return () => clearInterval(id) }, [])

  const permissions = dashboard?.permissions || []
  const tabs = useMemo(() => {
    const rows = [['overview', t.overview || 'نظرة عامة']]
    if (permissions.includes('reports')) rows.push(['analytics', t.analyticsTitle || 'التحليلات'])
    if (permissions.includes('inventory')) rows.push(['inventory', t.inventoryTitle || 'المخزون'])
    rows.push(['branches', t.branches || 'الفروع'])
    rows.push(['team', t.teamTitle || 'الفريق'])
    rows.push(['hours', t.businessHours || 'ساعات العمل'])
    return rows
  }, [permissions, t])

  if (!dashboard && !error) return <div className="stats">{[0, 1, 2, 3].map(i => <div className="stat skeleton" key={i}/>)}</div>
  if (!dashboard) return <p className="error">{error}</p>
  const store = dashboard.store
  const orders = dashboard.orders
  const sales = dashboard.sales

  return <>
    {notice && <p className="success-note">{notice}</p>}
    {error && <p className="error">{error}</p>}
    <div className="admin-tabs" role="tablist">{tabs.map(([id, label]) =>
      <button key={id} type="button" role="tab" aria-selected={tab === id} className={tab === id ? 'is-active' : ''} onClick={() => setTab(id)}>{label}</button>)}
    </div>
    {tab === 'overview' && <Overview dashboard={dashboard} t={t} onChanged={loadDashboard} setNotice={setNotice} setError={setError}/>}
    {tab === 'analytics' && <Analytics t={t} lang={lang}/>}
    {tab === 'inventory' && <Inventory t={t}/>}
    {tab === 'branches' && <Branches t={t} canManage={permissions.includes('staff')} onError={setError}/>}
    {tab === 'team' && <Team t={t} canManage={permissions.includes('staff')} roles={dashboard.roles} onError={setError}/>}
    {tab === 'hours' && <Hours t={t} canManage={permissions.includes('staff')} onError={setError}/>}
    <p className="note">{t.storeServiceNote}: {t[`service_${store.service_type}`] || store.service_type} · {t.storeRating}: {store.rating} · {t.yourRole}: {ROLE_LABEL[dashboard.role] || dashboard.role}</p>
  </>
}

function Overview({ dashboard, t, onChanged, setNotice, setError }) {
  const { orderCount, s } = useMemo(() => ({ orderCount: dashboard.orders, s: dashboard.sales }), [dashboard])
  const [busy, setBusy] = useState(false)
  async function togglePause() {
    setBusy(true)
    try {
      await api('/merchant/status/', { method: 'PATCH', body: JSON.stringify({ temporarily_closed: !dashboard.store.temporarily_closed }) })
      setNotice(dashboard.store.temporarily_closed ? t.storeResumed : t.storePaused)
      await onChanged()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return <>
    <div className="section-head"><div><h3>{dashboard.store.shop_name}</h3>
      <p>{dashboard.store.accepts_orders ? t.storeAcceptingOrders : t.storeNotAcceptingOrders} · {t.prepMinutesDefault}: {dashboard.store.prep_minutes}</p></div>
      <button type="button" className={dashboard.store.temporarily_closed ? '' : 'secondary'} disabled={busy} onClick={togglePause}>
        {dashboard.store.temporarily_closed ? t.resumeOrders : t.pauseOrders}
      </button></div>
    <div className="stats">
      {[['new', t.new, orderCount.new], ['preparing', t.preparing, orderCount.preparing], ['ready', t.ready, orderCount.ready], ['completed', t.completed, orderCount.completed], ['cancelled', t.cancelled, orderCount.cancelled]].map(([id, label, value]) =>
        <article className={`stat ${id === 'new' && value ? 'is-highlight' : ''}`} key={id}><div className="stat-head"><small>{label}</small></div><strong>{value}</strong></article>)}
    </div>
    <div className="stats">
      <article className="stat"><div className="stat-head"><small>{t.salesToday}</small></div><strong>{money(s.today.gross)}</strong><small>{s.today.orders} {t.orders}</small></article>
      <article className="stat"><div className="stat-head"><small>{t.salesWeek}</small></div><strong>{money(s.week.gross)}</strong><small>{s.week.orders} {t.orders}</small></article>
      <article className="stat"><div className="stat-head"><small>{t.salesMonth}</small></div><strong>{money(s.month.gross)}</strong><small>{s.month.orders} {t.orders}</small></article>
      <article className="stat"><div className="stat-head"><small>{t.productsDue}</small></div><strong>{money(dashboard.settlements.outstanding)}</strong></article>
    </div>
    <div className="stats">
      <article className="stat"><div className="stat-head"><small>{t.activeProducts}</small></div><strong>{dashboard.products.active}</strong></article>
      <article className="stat"><div className="stat-head"><small>{t.lowStock}</small></div><strong>{dashboard.products.low_stock}</strong></article>
      <article className="stat"><div className="stat-head"><small>{t.outOfStock}</small></div><strong>{dashboard.products.out_of_stock}</strong></article>
      <article className="stat"><div className="stat-head"><small>{t.productsCount}</small></div><strong>{dashboard.products.total}</strong></article>
    </div>
    <p className="note">{t.salesBreakdownNote}: {t.productRevenue} {money(s.today.products)} · {t.deliveryFee} {money(s.today.delivery)}</p>
    {!!dashboard.alerts.length && <section className="panel"><h3>{t.importantAlerts}</h3><ul className="plain-list">
      {dashboard.alerts.map((alert, index) => <li key={index}>
        {alert.type === 'store.paused' ? (t.storePausedAlert || alert.message) :
          `${alert.type === 'stock.out' ? t.outOfStock : t.lowStock}: ${alert.name} · ${alert.quantity}`}
      </li>)}
    </ul></section>}
  </>
}

function Analytics({ t, lang }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { api('/merchant/analytics/').then(setData).catch(e => setError(e.message)) }, [])
  if (error) return <p className="error">{error}</p>
  if (!data) return <div className="stats">{[0, 1, 2].map(i => <div className="stat skeleton" key={i}/>)}</div>
  return <>
    <section className="panel"><h3>{t.topProducts}</h3>
      <div className="table-wrap"><table><thead><tr><th>{t.name}</th><th>{t.quantity}</th><th>{t.productsAmount}</th></tr></thead>
        <tbody>{data.top_products.map(row => <tr key={row.name}><td>{row.name}</td><td>{row.quantity}</td><td>{money(row.revenue)}</td></tr>)}
          {!data.top_products.length && <tr><td colSpan="3">{t.empty}</td></tr>}</tbody></table></div></section>
    <section className="panel"><h3>{t.slowProducts}</h3>
      <div className="table-wrap"><table><thead><tr><th>{t.name}</th><th>{t.quantity}</th><th>{t.productsAmount}</th></tr></thead>
        <tbody>{data.slow_products.map(row => <tr key={row.name}><td>{row.name}</td><td>{row.quantity}</td><td>{money(row.revenue)}</td></tr>)}
          {!data.slow_products.length && <tr><td colSpan="3">{t.empty}</td></tr>}</tbody></table></div></section>
    <section className="panel"><h3>{t.monthlySales}</h3>
      <div className="table-wrap"><table><thead><tr><th>{t.month}</th><th>{t.orders}</th><th>{t.total}</th><th>{t.productRevenue}</th></tr></thead>
        <tbody>{data.monthly.map(row => <tr key={row.month}><td dir="ltr">{row.month}</td><td>{row.orders}</td><td>{money(row.gross)}</td><td>{money(row.products)}</td></tr>)}</tbody></table></div></section>
    <section className="panel"><h3>{t.cancelledOrdersReport}</h3>
      <div className="table-wrap"><table><thead><tr><th>{t.orderPrefix}</th><th>{t.customerName}</th><th>{t.total}</th><th>{t.cancellationReason}</th><th>{t.date}</th></tr></thead>
        <tbody>{data.cancelled_orders.map(row => <tr key={row.id}><td>{row.order_number}</td><td>{row.customer}</td><td>{money(row.total)}</td><td>{row.reason || '—'}</td><td dir="ltr">{new Date(row.created_at).toLocaleDateString(lang === 'en' ? 'en' : 'ar')}</td></tr>)}
          {!data.cancelled_orders.length && <tr><td colSpan="5">{t.empty}</td></tr>}</tbody></table></div></section>
    <p className="note">{data.fee_note}</p>
  </>
}

function Inventory({ t }) {
  const [products, setProducts] = useState([])
  const [movements, setMovements] = useState([])
  const [error, setError] = useState('')
  const [form, setForm] = useState({ delta: '', reason: 'restock', note: '' })
  const [selected, setSelected] = useState('')
  const [busy, setBusy] = useState(false)
  async function load() {
    try {
      const [items, ledger] = await Promise.all([api('/products/'), api('/merchant/inventory/movements/')])
      setProducts(Array.isArray(items) ? items : (items?.results || []))
      setMovements(ledger)
      setError('')
    } catch (e) { setError(e.message) }
  }
  useEffect(() => { load() }, [])
  async function adjust(event) {
    event.preventDefault()
    if (!selected) return
    setBusy(true); setError('')
    try {
      await api(`/products/${selected}/stock/`, { method: 'POST', body: JSON.stringify({ delta: Number(form.delta), reason: form.reason, note: form.note }) })
      setForm({ delta: '', reason: 'restock', note: '' })
      await load()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return <>
    <section className="panel"><div className="section-head"><div><h3>{t.inventoryTitle}</h3><p>{t.inventoryHint}</p></div>
      <button type="button" className="secondary" onClick={load}>{t.refresh}</button></div>
      {error && <p className="error">{error}</p>}
      <form className="inline-form stock-form" onSubmit={adjust}>
        <select value={selected} onChange={e => setSelected(e.target.value)} required>
          <option value="">{t.chooseProduct}</option>
          {products.map(product => <option key={product.id} value={product.id}>{product.name} · {product.quantity ?? '—'}</option>)}
        </select>
        <input type="number" value={form.delta} onChange={e => setForm({ ...form, delta: e.target.value })} placeholder={t.quantityDelta} required/>
        <select value={form.reason} onChange={e => setForm({ ...form, reason: e.target.value })}>
          <option value="restock">{t.reasonRestock}</option>
          <option value="manual">{t.reasonManual}</option>
          <option value="correction">{t.reasonCorrection}</option>
        </select>
        <input value={form.note} onChange={e => setForm({ ...form, note: e.target.value })} placeholder={t.notes} maxLength={255}/>
        <button disabled={busy || !selected || !form.delta}>{busy ? t.saving : t.applyStock}</button>
      </form>
      <div className="table-wrap"><table><thead><tr><th>{t.name}</th><th>{t.quantity}</th><th>{t.lowStockThreshold}</th><th>{t.status}</th><th>{t.price}</th><th>{t.offerPrice}</th></tr></thead>
        <tbody>{products.map(product => <tr key={product.id}>
          <td>{product.name}</td><td>{product.quantity ?? '—'}</td><td>{product.low_stock_threshold}</td>
          <td><span className={`stock-badge ${product.stock_status === 'out' ? 'is-out' : product.stock_status === 'low' ? 'is-low' : 'is-in'}`}>{t[`stock_${product.stock_status}`] || product.stock_status}</span></td>
          <td>{money(product.price)}</td><td>{product.discount_active ? money(product.effective_price) : '—'}</td>
        </tr>)}</tbody></table></div>
    </section>
    <section className="panel"><h3>{t.stockMovements}</h3>
      <div className="table-wrap"><table><thead><tr><th>{t.date}</th><th>{t.name}</th><th>{t.quantityDelta}</th><th>{t.before}</th><th>{t.after}</th><th>{t.reason}</th><th>{t.orderPrefix}</th><th>{t.recordedBy}</th></tr></thead>
        <tbody>{movements.map(row => <tr key={row.id}>
          <td dir="ltr">{new Date(row.created_at).toLocaleString()}</td><td>{row.product_name}</td>
          <td className={row.delta < 0 ? 'is-negative' : 'is-positive'}>{row.delta > 0 ? `+${row.delta}` : row.delta}</td>
          <td>{row.quantity_before ?? '—'}</td><td>{row.quantity_after ?? '—'}</td>
          <td>{t[`reason_${row.reason}`] || row.reason}</td><td>{row.order_number || '—'}</td><td>{row.actor_name || '—'}</td>
        </tr>)}</tbody></table></div>
      {!movements.length && <p className="note">{t.empty}</p>}
    </section>
  </>
}

function Branches({ t, canManage, onError }) {
  const [rows, setRows] = useState([])
  const [form, setForm] = useState({ name: '', address: '', phone: '', latitude: '', longitude: '', opening_hours: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function load() {
    try { setRows(await api('/merchant/branches/')); setError('') } catch (e) { setError(e.message); onError?.(e.message) }
  }
  useEffect(() => { load() }, [])
  async function create(event) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const payload = { ...form }
      if (!payload.latitude || !payload.longitude) { delete payload.latitude; delete payload.longitude }
      await api('/merchant/branches/', { method: 'POST', body: JSON.stringify(payload) })
      setForm({ name: '', address: '', phone: '', latitude: '', longitude: '', opening_hours: '' })
      await load()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  async function toggle(row) {
    try { await api(`/merchant/branches/${row.id}/`, { method: 'PATCH', body: JSON.stringify({ is_active: !row.is_active }) }); await load() }
    catch (e) { setError(e.message) }
  }
  async function remove(row) {
    try { await api(`/merchant/branches/${row.id}/`, { method: 'DELETE' }); await load() }
    catch (e) { setError(e.message) }
  }
  return <section className="panel"><div className="section-head"><div><h3>{t.branches}</h3><p>{t.branchesHint}</p></div></div>
    {error && <p className="error">{error}</p>}
    <div className="table-wrap"><table><thead><tr><th>{t.branchName}</th><th>{t.address}</th><th>{t.phone}</th><th>{t.openingHours}</th><th>{t.status}</th><th/></tr></thead>
      <tbody>{rows.map(row => <tr key={row.id}><td>{row.name}</td><td>{row.address || '—'}</td><td dir="ltr">{row.phone || '—'}</td><td>{row.opening_hours || '—'}</td>
        <td>{row.is_active ? t.active : t.disabled}</td>
        <td className="row-actions">{canManage && <>
          <button type="button" className="secondary" onClick={() => toggle(row)}>{row.is_active ? t.deactivate : t.activate}</button>
          <button type="button" className="secondary danger" onClick={() => remove(row)}>{t.delete}</button></>}
        </td></tr>)}
        {!rows.length && <tr><td colSpan="6">{t.noBranches}</td></tr>}</tbody></table></div>
    {canManage && <form className="form-stack branch-form" onSubmit={create}>
      <h3>{t.addBranch}</h3>
      <div className="two-fields">
        <label>{t.branchName}<input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} required/></label>
        <label>{t.phone}<input value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })}/></label>
        <label>{t.address}<input value={form.address} onChange={e => setForm({ ...form, address: e.target.value })}/></label>
        <label>{t.openingHours}<input value={form.opening_hours} onChange={e => setForm({ ...form, opening_hours: e.target.value })}/></label>
        <label>{t.latitude}<input value={form.latitude} onChange={e => setForm({ ...form, latitude: e.target.value })} inputMode="decimal"/></label>
        <label>{t.longitude}<input value={form.longitude} onChange={e => setForm({ ...form, longitude: e.target.value })} inputMode="decimal"/></label>
      </div>
      <p className="note">{t.branchApprovalNote}</p>
      <button disabled={busy}>{busy ? t.saving : t.addBranch}</button>
    </form>}
  </section>
}

function Team({ t, canManage, roles = [], onError }) {
  const [data, setData] = useState({ staff: [], roles: [] })
  const [form, setForm] = useState({ username: '', password: '', first_name: '', last_name: '', phone: '', role: 'orders' })
  const [error, setError] = useState('')
  const [created, setCreated] = useState(null)
  const [busy, setBusy] = useState(false)
  async function load() {
    try { setData(await api('/merchant/staff/')); setError('') } catch (e) { setError(e.message); onError?.(e.message) }
  }
  useEffect(() => { load() }, [])
  async function create(event) {
    event.preventDefault(); setBusy(true); setError(''); setCreated(null)
    try {
      const result = await api('/merchant/staff/', { method: 'POST', body: JSON.stringify(form) })
      setCreated(result)
      setForm({ username: '', password: '', first_name: '', last_name: '', phone: '', role: 'orders' })
      await load()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  async function patch(row, body) {
    try { await api(`/merchant/staff/${row.id}/`, { method: 'PATCH', body: JSON.stringify(body) }); await load() }
    catch (e) { setError(e.message) }
  }
  async function remove(row) {
    try { await api(`/merchant/staff/${row.id}/`, { method: 'DELETE' }); await load() }
    catch (e) { setError(e.message) }
  }
  const roleRows = data.roles?.length ? data.roles : roles || []
  return <section className="panel"><div className="section-head"><div><h3>{t.teamTitle}</h3><p>{t.teamHint}</p></div></div>
    {error && <p className="error">{error}</p>}
    {created && <p className="success-note">{t.staffCreated}: {created.username}</p>}
    <div className="table-wrap"><table><thead><tr><th>{t.name}</th><th>{t.users}</th><th>{t.accountRole}</th><th>{t.permissions}</th><th>{t.status}</th><th/></tr></thead>
      <tbody>{data.staff.map(row => <tr key={row.id}><td>{row.name || row.username}</td><td dir="ltr">{row.username}</td>
        <td>{canManage ? <select value={row.role} onChange={e => patch(row, { role: e.target.value })}>
          {Object.entries(ROLE_LABEL).filter(([key]) => key !== 'owner').map(([key]) => <option key={key} value={key}>{ROLE_LABEL[key]}</option>)}
        </select> : (ROLE_LABEL[row.role] || row.role)}</td>
        <td><small>{row.permissions.join(' · ')}</small></td>
        <td>{row.is_active ? t.active : t.disabled}</td>
        <td className="row-actions">{canManage && <>
          <button type="button" className="secondary" onClick={() => patch(row, { is_active: !row.is_active })}>{row.is_active ? t.disableAccount : t.enableAccount}</button>
          <button type="button" className="secondary danger" onClick={() => remove(row)}>{t.delete}</button></>}
        </td></tr>)}
        {!data.staff.length && <tr><td colSpan="6">{t.noStaff}</td></tr>}</tbody></table></div>
    {canManage && <form className="form-stack team-form" onSubmit={create}>
      <h3>{t.addStaff}</h3>
      <div className="two-fields">
        <label>{t.firstName}<input value={form.first_name} onChange={e => setForm({ ...form, first_name: e.target.value })} required/></label>
        <label>{t.lastName}<input value={form.last_name} onChange={e => setForm({ ...form, last_name: e.target.value })}/></label>
        <label>{t.loginUsername}<input value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} minLength="3" required/></label>
        <label>{t.temporaryPassword}<input type="password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} minLength="8" required/></label>
        <label>{t.phone}<input value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })}/></label>
        <label>{t.accountRole}<select value={form.role} onChange={e => setForm({ ...form, role: e.target.value })}>
          {roleRows.map(role => <option key={role.role} value={role.role}>{ROLE_LABEL[role.role] || role.label}</option>)}
        </select></label>
      </div>
      <p className="note">{t.staffPasswordNote}</p>
      <button disabled={busy}>{busy ? t.saving : t.addStaff}</button>
    </form>}
  </section>
}

function Hours({ t, canManage, onError }) {
  const [rows, setRows] = useState(DAYS.map((_, weekday) => ({ weekday, opens_at: '08:00', closes_at: '22:00', is_closed: false })))
  const [closures, setClosures] = useState([])
  const [closure, setClosure] = useState({ date: '', reason: '' })
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  async function load() {
    try {
      const data = await api('/merchant/hours/')
      const saved = new Map((data.hours || []).map(row => [row.weekday, row]))
      setRows(DAYS.map((_, weekday) => {
        const row = saved.get(weekday)
        return row ? {
          weekday, opens_at: (row.opens_at || '08:00').slice(0, 5),
          closes_at: (row.closes_at || '22:00').slice(0, 5), is_closed: row.is_closed,
        } : { weekday, opens_at: '08:00', closes_at: '22:00', is_closed: false }
      }))
      setClosures(data.closures || [])
      setError('')
    } catch (e) { setError(e.message); onError?.(e.message) }
  }
  useEffect(() => { load() }, [])
  function update(weekday, key, value) {
    setRows(items => items.map(row => row.weekday === weekday ? { ...row, [key]: value } : row))
  }
  async function save() {
    setBusy(true); setError(''); setNotice('')
    try {
      await api('/merchant/hours/', { method: 'PUT', body: JSON.stringify({ hours: rows }) })
      setNotice(t.hoursSaved)
      await load()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  async function addClosure(event) {
    event.preventDefault(); setError('')
    try {
      await api('/merchant/closures/', { method: 'POST', body: JSON.stringify(closure) })
      setClosure({ date: '', reason: '' })
      await load()
    } catch (e) { setError(e.message) }
  }
  async function removeClosure(id) {
    try { await api(`/merchant/closures/?id=${id}`, { method: 'DELETE' }); await load() }
    catch (e) { setError(e.message) }
  }
  return <section className="panel"><div className="section-head"><div><h3>{t.businessHours}</h3><p>{t.businessHoursHint}</p></div></div>
    {error && <p className="error">{error}</p>}
    {notice && <p className="success-note">{notice}</p>}
    <div className="hours-grid">{rows.map(row => <React.Fragment key={row.weekday}>
      <span>{DAYS[row.weekday]}</span>
      <label className="check-label"><input type="checkbox" checked={row.is_closed} onChange={e => update(row.weekday, 'is_closed', e.target.checked)}/>{t.closedDay}</label>
      <input type="time" value={row.opens_at} disabled={row.is_closed} onChange={e => update(row.weekday, 'opens_at', e.target.value)} aria-label={t.from}/>
      <input type="time" value={row.closes_at} disabled={row.is_closed} onChange={e => update(row.weekday, 'closes_at', e.target.value)} aria-label={t.to}/>
    </React.Fragment>)}</div>
    {canManage && <button type="button" disabled={busy} onClick={save}>{busy ? t.saving : t.saveHours}</button>}
    <h3>{t.exceptionalClosures}</h3>
    <div className="table-wrap"><table><thead><tr><th>{t.date}</th><th>{t.reason}</th><th/></tr></thead>
      <tbody>{closures.map(row => <tr key={row.id}><td dir="ltr">{row.date}</td><td>{row.reason || '—'}</td>
        <td>{canManage && <button type="button" className="secondary danger" onClick={() => removeClosure(row.id)}>{t.delete}</button>}</td></tr>)}
        {!closures.length && <tr><td colSpan="3">{t.noClosures}</td></tr>}</tbody></table></div>
    {canManage && <form className="inline-form" onSubmit={addClosure}>
      <input type="date" value={closure.date} onChange={e => setClosure({ ...closure, date: e.target.value })} required/>
      <input value={closure.reason} onChange={e => setClosure({ ...closure, reason: e.target.value })} placeholder={t.reason} maxLength={200}/>
      <button>{t.addClosure}</button>
    </form>}
    <p className="note">{t.scheduledOrdersNote}</p>
  </section>
}
