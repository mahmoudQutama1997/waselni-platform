import {useEffect,useState} from 'react'
import {api} from '../api'
import DeliveryMap from '../map/DeliveryMap.tsx'
import {makeMapLabels} from '../map/labels'
import {Card,Empty,ErrorBox,Field,Glyph,KPI,Loader,Status,money,useResource,when} from './adminUi.jsx'

const STATUSES=['new','accepted','preparing','ready','assigned','picked_up','delivering','awaiting_confirmation','completed','cancelled']

export function OperationsPanel({lang,L}){
 const [filters,setFilters]=useState({status:'active',service:'',region:'',q:'',from:'',to:''})
 const [query,setQuery]=useState(filters)
 const resource=useResource(()=>{
  const params=new URLSearchParams({limit:'200',status:query.status||'all'})
  for(const key of ['service','region','q','from','to'])if(query[key])params.set(key,query[key])
  return api(`/admin/control/operations/?${params.toString()}`)
 },[lang,query])
 const [detail,setDetail]=useState(null),[detailError,setDetailError]=useState('')
 useEffect(()=>{if(!detail){return}let live=true;api(`/admin/control/operations/${detail.id}/`).then(row=>{if(live)setDetail({...detail,full:row})}).catch(err=>{if(live)setDetailError(err.message)});return()=>{live=false}},[detail?.id])
 const counts=resource.data?.counts||{}
 const tabs=[['active',L.activeOrders],['late',L.late],['needs_attention',L.needsAttention],['completed',L.completed],['cancelled',L.cancelled],['all',L.all]]
 return <div className="acc-stack">
  <Card title={L.operations} actions={<button type="button" className="secondary" onClick={resource.reload}>{L.refresh}</button>}>
   <div className="acc-tabs">{tabs.map(([id,label])=><button type="button" key={id} className={query.status===id?'primary':'secondary'} onClick={()=>{setFilters({...filters,status:id});setQuery({...filters,status:id})}}>{label}{counts[id]!=null?` · ${counts[id]}`:''}</button>)}</div>
   <div className="acc-filter-grid">
    <div className="search-field"><span aria-hidden="true">⌕</span><input value={filters.q} onChange={event=>setFilters({...filters,q:event.target.value})} onKeyDown={event=>{if(event.key==='Enter'){event.preventDefault();setQuery({...filters})}}} placeholder={L.searchOrders} aria-label={L.searchOrders}/></div>
    <select value={filters.service} onChange={event=>setFilters({...filters,service:event.target.value})} aria-label={L.service}><option value="">{L.service} · {L.all}</option>{(resource.data?.services||[]).map(row=><option key={row.code} value={row.code}>{lang==='ar'?row.name_ar:row.name_en}</option>)}</select>
    <select value={filters.region} onChange={event=>setFilters({...filters,region:event.target.value})} aria-label={L.region}><option value="">{L.region} · {L.all}</option>{(resource.data?.regions||[]).map(row=><option key={row.code} value={row.code}>{lang==='ar'?row.name_ar:row.name_en}</option>)}</select>
    <input type="date" value={filters.from} onChange={event=>setFilters({...filters,from:event.target.value})} aria-label={L.from}/>
    <input type="date" value={filters.to} onChange={event=>setFilters({...filters,to:event.target.value})} aria-label={L.to}/>
    <button type="button" onClick={()=>setQuery({...filters})}>{L.apply}</button>
   </div>
   <ErrorBox text={resource.error}/>
   {!resource.data&&!resource.error&&<Loader/>}
   {resource.data&&!resource.data.orders.length&&<Empty text={L.noData}/>}
   {resource.data&&!!resource.data.orders.length&&<div className="table-wrap"><table><thead><tr><th>{L.orders}</th><th>{L.service}</th><th>{L.status}</th><th>{L.customer}</th><th>{L.provider}</th><th>{L.captain}</th><th>{L.total}</th><th>{L.date}</th><th/></tr></thead><tbody>{resource.data.orders.map(order=><tr key={order.id}><td>{order.order_number}<small className="acc-sub">{order.branch||'—'}</small></td><td>{order.service_type}</td><td><Status value={order.status} labels={L}/></td><td>{order.customer_name}</td><td>{order.merchant||'—'}{order.region&&<small className="acc-sub">{order.region.name_en}</small>}</td><td>{order.captain_name||'—'}</td><td>{money(order.total)}</td><td>{when(order.created_at)}</td><td><button type="button" className="secondary" onClick={()=>{setDetailError('');setDetail(order)}}>{L.details}</button></td></tr>)}</tbody></table></div>}
  </Card>
  {detail&&<Card title={`${L.details} · ${detail.order_number}`} actions={<button type="button" className="ghost" onClick={()=>setDetail(null)}>{L.close}</button>}>
   <ErrorBox text={detailError}/>
   <div className="acc-detail-grid"><div><small>{L.customer}</small><b>{detail.customer_name}</b></div><div><small>{L.provider}</small><b>{detail.merchant||'—'}</b></div><div><small>{L.captain}</small><b>{detail.captain_name||'—'}</b></div><div><small>{L.total}</small><b>{money(detail.total)}</b></div><div><small>{L.deliveryFee}</small><b>{money(detail.delivery_fee)}</b></div><div><small>{L.status}</small><Status value={detail.status} labels={L}/></div></div>
   <p className="muted-note">{detail.pickup_address||'—'} → {detail.dropoff_address||'—'}</p>
   {detail.full&&<><div className="acc-grid two"><div><h4>{L.items}</h4>{(detail.full.items||[]).map((item,index)=><div className="acc-row-line" key={index}><span>{item.name} × {item.quantity}</span><small>{money(item.line_total)}</small></div>)}{!(detail.full.items||[]).length&&<p className="muted-note">{L.empty}</p>}</div><div><h4>{L.settlements}</h4>{detail.full.settlement?<><div className="acc-row-line"><span>{detail.full.settlement.reference}</span><b>{money(detail.full.settlement.amount)}</b></div><div className="acc-row-line"><span>{L.outstanding}</span><b>{money(detail.full.settlement.outstanding)}</b></div></>:<p className="muted-note">{L.empty}</p>}</div></div>
   <h4>{L.activities}</h4><div className="acc-timeline">{detail.full.activities.map(row=><div key={row.id}><small>{when(row.created_at)}</small><span>{row.event} {row.from_status&&row.to_status?`· ${row.from_status} → ${row.to_status}`:''}</span><small>{row.actor}</small></div>)}{!detail.full.activities.length&&<p className="muted-note">{L.empty}</p>}</div></>}
  </Card>}
 </div>
}

export function MapPanel({lang,L}){
 const [service,setService]=useState(''),[region,setRegion]=useState('')
 const resource=useResource(()=>{const params=new URLSearchParams();if(service)params.set('service',service);if(region)params.set('region',region);return api(`/admin/control/map/?${params.toString()}`)},[lang,service,region])
 const data=resource.data
 const labels=makeMapLabels(L,lang,'admin')
 const points=[]
 ;(data?.branches||[]).forEach(branch=>{if(branch.latitude!=null&&branch.longitude!=null)points.push({id:`branch-${branch.id}`,kind:'store',lat:branch.latitude,lng:branch.longitude,label:branch.label,sublabel:branch.sublabel,popup:{title:branch.label,lines:[branch.sublabel,branch.region]}})})
 ;(data?.captains||[]).forEach(captain=>{if(captain.latitude!=null&&captain.longitude!=null){const stamp=captain.location_updated_at?new Date(captain.location_updated_at).getTime():0;const stale=!stamp||Date.now()-stamp>5*60000;points.push({id:`captain-${captain.id}`,kind:'captain',lat:captain.latitude,lng:captain.longitude,label:captain.label,sublabel:stale?L.stale:L.live,stale,assigned:true,popup:{title:captain.label,lines:[captain.sublabel,stamp?when(captain.location_updated_at):L.unassigned]}})}})
 ;(data?.orders||[]).forEach(order=>{if(order.dropoff)points.push({id:`order-${order.id}`,kind:'customer',lat:order.dropoff[0],lng:order.dropoff[1],label:order.label,sublabel:order.sublabel,popup:{title:order.label,lines:[order.sublabel,order.status]}})})
 const lines=(data?.orders||[]).filter(order=>order.pickup&&order.dropoff).slice(0,20).map(order=>[order.pickup,order.dropoff])
 return <div className="acc-stack">
  <Card title={L.map} subtitle={L.mapHint} actions={<div className="row-actions"><select value={service} onChange={event=>setService(event.target.value)}><option value="">{L.service} · {L.all}</option>{(data?.services||[]).map(row=><option key={row.code} value={row.code}>{lang==='ar'?row.name_ar:row.name_en}</option>)}</select><select value={region} onChange={event=>setRegion(event.target.value)}><option value="">{L.region} · {L.all}</option>{(data?.regions||[]).map(row=><option key={row.code} value={row.code}>{lang==='ar'?row.name_ar:row.name_en}</option>)}</select><button type="button" className="secondary" onClick={resource.reload}>{L.refresh}</button></div>}>
   <ErrorBox text={resource.error}/>
   {!data&&!resource.error&&<Loader/>}
   {data&&<><div className="acc-map-stats"><span>{data.branches.length} {L.branchesCount}</span><span>{data.captains.length} {L.captainsCount}</span><span>{data.orders.length} {L.activeOrders}</span></div>
   <DeliveryMap points={points} secondaryLines={lines} labels={labels} height={460} cluster fitKey={`${service}|${region}|${points.length}`} emptyText={L.empty}/></>}
  </Card>
 </div>
}

export function AnalyticsPanel({lang,L}){
 const [days,setDays]=useState(30)
 const resource=useResource(()=>api(`/admin/control/analytics/?days=${days}`),[lang,days])
 const data=resource.data
 const maxBar=Math.max(1,...(data?.series||[]).map(day=>day.orders))
 return <div className="acc-stack">
  <Card title={L.analytics} actions={<div className="row-actions">{[7,30,90].map(value=><button type="button" key={value} className={days===value?'primary':'secondary'} onClick={()=>setDays(value)}>{value===7?L.week:value===30?L.month:`${value} ${L.daily}`}</button>)}</div>}>
   <ErrorBox text={resource.error}/>
   {!data&&!resource.error&&<Loader/>}
   {data&&<div className="acc-kpis"><KPI label={L.totalOrders} value={data.orders.total} icon="orders"/><KPI label={L.activeOrders} value={data.orders.active} icon="map"/><KPI label={L.completed} value={data.orders.completed} icon="orders"/><KPI label={L.cancelled} value={data.orders.cancelled} icon="shield"/><KPI label={L.cancelRate} value={`${data.orders.cancellation_rate}%`} icon="chart"/><KPI label={L.sales} value={money(data.money.sales)} icon="money"/><KPI label={L.revenue} value={money(data.money.product_revenue)} icon="money"/><KPI label={L.deliveryFee} value={money(data.money.delivery_revenue)} icon="scooter"/><KPI label={L.commission} value={data.money.commission_configured?money(data.money.commission):'—'} icon="money"/><KPI label={L.customers} value={data.people.customers} icon="users"/><KPI label={L.merchants} value={data.people.merchants} icon="store"/><KPI label={L.avgMinutes} value={data.orders.average_completion_minutes??'—'} icon="chart"/></div>}
   <p className="muted-note">{L.revenueNote}</p>
  </Card>
  {data&&<div className="acc-grid two">
   <Card title={L.ordersSeries}>{<div className="acc-bars">{data.series.map(day=><div className="acc-bar" key={day.date} title={`${day.date}: ${day.orders}`}><b>{day.orders}</b><div className="acc-bar-track"><i style={{height:`${Math.max(3,(day.orders/maxBar)*100)}%`}}/></div><small>{day.date.slice(5)}</small></div>)}</div>}</Card>
   <Card title={L.byService}><div className="table-wrap"><table><thead><tr><th>{L.service}</th><th>{L.orders}</th><th>{L.revenue}</th></tr></thead><tbody>{data.by_service.map(row=><tr key={row.service_type||'—'}><td>{row.service_type||'—'}</td><td>{row.total}</td><td>{money(row.revenue)}</td></tr>)}</tbody></table></div></Card>
   <Card title={L.byRegion}><div className="table-wrap"><table><thead><tr><th>{L.region}</th><th>{L.orders}</th><th>{L.revenue}</th></tr></thead><tbody>{data.by_region.map(row=><tr key={row.branch__region__code||'—'}><td>{lang==='ar'?(row.branch__region__name_ar||'—'):(row.branch__region__name_en||'—')}</td><td>{row.total}</td><td>{money(row.revenue)}</td></tr>)}</tbody></table></div></Card>
   <Card title={L.byStatus}><div className="table-wrap"><table><thead><tr><th>{L.status}</th><th>{L.orders}</th></tr></thead><tbody>{data.by_status.map(row=><tr key={row.status}><td><Status value={row.status} labels={L}/></td><td>{row.total}</td></tr>)}</tbody></table></div></Card>
  </div>}
 </div>
}

export function FinancePanel({lang,L}){
 const resource=useResource(()=>api('/admin/control/finance/'),[lang])
 const data=resource.data
 return <div className="acc-stack">
  <Card title={L.finance} actions={<button type="button" className="secondary" onClick={resource.reload}>{L.refresh}</button>}>
   <ErrorBox text={resource.error}/>
   {!data&&!resource.error&&<Loader/>}
   {data&&<><div className="acc-kpis"><KPI label={L.sales} value={money(data.sales)} icon="money"/><KPI label={L.revenue} value={money(data.product_revenue)} icon="store"/><KPI label={L.deliveryFee} value={money(data.delivery_revenue)} icon="scooter"/><KPI label={L.commission} value={data.commission_configured?money(data.commission):'—'} icon="money"/><KPI label={L.outstanding} value={money(data.subscription_outstanding)} icon="chart"/><KPI label={L.settlements} value={data.open_settlements} icon="shield"/></div>
   <div className="table-wrap"><table><thead><tr><th>{L.orders}</th><th>{L.provider}</th><th>{L.captain}</th><th>{L.amount}</th><th>{L.outstanding}</th><th>{L.status}</th></tr></thead><tbody>{data.settlements.map(row=><tr key={row.id}><td>{row.order_number}</td><td>{row.merchant}</td><td>{row.captain}</td><td>{money(row.amount)}</td><td>{money(row.outstanding)}</td><td><Status value={row.closed?'completed':'pending'} labels={L}/></td></tr>)}</tbody></table></div></>}
  </Card>
  {data&&<div className="acc-grid two">
   <Card title={L.receipts}>{data.receipts.length?<div className="table-wrap"><table><thead><tr><th>{L.captain}</th><th>{L.amount}</th><th>{L.agent}</th><th>{L.date}</th></tr></thead><tbody>{data.receipts.map(row=><tr key={row.id}><td>{row.captain}</td><td>{money(row.amount)}</td><td>{row.recorded_by}</td><td>{when(row.created_at)}</td></tr>)}</tbody></table></div>:<Empty text={L.empty}/>}</Card>
   <Card title={L.subscriptions}>{data.subscription_payments.length?<div className="table-wrap"><table><thead><tr><th>{L.username}</th><th>{L.amount}</th><th>{L.status}</th><th>{L.date}</th></tr></thead><tbody>{data.subscription_payments.map(row=><tr key={row.id}><td>{row.user}</td><td>{money(row.amount)}</td><td>{row.method}</td><td>{when(row.created_at)}</td></tr>)}</tbody></table></div>:<Empty text={L.empty}/>}</Card>
   <Card title={L.status}>{<div className="table-wrap"><table><thead><tr><th>{L.status}</th><th>{L.orders}</th><th>{L.amount}</th></tr></thead><tbody>{data.payment_methods.map(row=><tr key={row.payment_method}><td>{row.payment_method}</td><td>{row.total}</td><td>{money(row.amount)}</td></tr>)}</tbody></table></div>}</Card>
  </div>}
 </div>
}

export function StaffPanel({lang,L}){
 const resource=useResource(()=>api('/admin/control/staff/'),[lang])
 const [form,setForm]=useState({identity_number:'',first_name:'',last_name:'',phone:'',admin_role:'operations',password:''})
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[created,setCreated]=useState(null)
 async function create(){
  setBusy(true);setError('');setCreated(null)
  try{const row=await api('/admin/control/staff/',{method:'POST',body:JSON.stringify(form)});setCreated(row);setForm({identity_number:'',first_name:'',last_name:'',phone:'',admin_role:'operations',password:''});resource.reload()}
  catch(err){setError(err.message)}finally{setBusy(false)}
 }
 async function changeRole(user,role){
  setError('')
  try{await api(`/admin/control/staff/${user.id}/`,{method:'PATCH',body:JSON.stringify({admin_role:role})});resource.reload()}
  catch(err){setError(err.message)}
 }
 async function toggle(user){
  setError('')
  try{await api(`/admin/control/staff/${user.id}/`,{method:'PATCH',body:JSON.stringify({is_active:!user.is_active})});resource.reload()}
  catch(err){setError(err.message)}
 }
 const data=resource.data
 return <div className="acc-stack">
  <Card title={L.staff} subtitle={L.staffHint} actions={<button type="button" className="secondary" onClick={resource.reload}>{L.refresh}</button>}>
   <ErrorBox text={resource.error||error}/>
   {!data&&!resource.error&&<Loader/>}
   {data&&<div className="table-wrap"><table><thead><tr><th>{L.name}</th><th>{L.role}</th><th>{L.permissions}</th><th>{L.status}</th><th/></tr></thead><tbody>{data.staff.map(user=><tr key={user.id}><td><b>{user.name}</b><small className="acc-sub">{user.username} · {user.phone||'—'}</small></td><td>{user.is_superuser?<Status value="approved" labels={L}/>:<select value={user.admin_role} onChange={event=>changeRole(user,event.target.value)}>{data.roles.map(role=><option key={role.code} value={role.code}>{role.label}</option>)}</select>}</td><td><small>{user.permissions.join(', ')}</small></td><td><Status value={user.is_active?'active':'inactive'} labels={L}/></td><td><button type="button" className="secondary" disabled={user.is_superuser} onClick={()=>toggle(user)}>{user.is_active?L.disable:L.enable}</button></td></tr>)}</tbody></table></div>}
  </Card>
  {data&&<Card title={L.addStaff}>
   <div className="acc-form-grid"><Field label={L.username}>{<input value={form.identity_number} onChange={event=>setForm({...form,identity_number:event.target.value})}/>}</Field><Field label={L.name}>{<input value={form.first_name} onChange={event=>setForm({...form,first_name:event.target.value})}/>}</Field><Field label={L.name}>{<input value={form.last_name} onChange={event=>setForm({...form,last_name:event.target.value})}/>}</Field><Field label={L.phone}>{<input value={form.phone} onChange={event=>setForm({...form,phone:event.target.value})}/>}</Field><Field label={L.role}>{<select value={form.admin_role} onChange={event=>setForm({...form,admin_role:event.target.value})}>{data.roles.map(role=><option key={role.code} value={role.code}>{role.label}</option>)}</select>}</Field><Field label={L.password} hint={L.generatePassword}>{<input type="password" value={form.password} onChange={event=>setForm({...form,password:event.target.value})}/>}</Field></div>
   <button type="button" disabled={busy||!form.identity_number||!form.first_name||!form.phone} onClick={create}>{busy?L.loading:L.addStaff}</button>
   {created&&<div className="credential-box"><b>{L.staffCreated}</b><p>{L.username}: <strong>{created.username}</strong></p><p>{L.password}: <code>{created.temporary_password}</code></p></div>}
  </Card>}
 </div>
}

export function SupportPanel({lang,L}){
 const [filters,setFilters]=useState({status:'',priority:'',assigned:''})
 const resource=useResource(()=>api(`/admin/control/support/?${new URLSearchParams(filters).toString()}`),[lang,filters])
 const [busy,setBusy]=useState(''),[error,setError]=useState('')
 const data=resource.data
 async function update(ticket,payload){
  setBusy(`t-${ticket.id}`);setError('')
  try{await api(`/admin/control/support/${ticket.id}/`,{method:'PATCH',body:JSON.stringify(payload)});resource.reload()}
  catch(err){setError(err.message)}finally{setBusy('')}
 }
 function resolve(ticket){
  const resolution=window.prompt(L.resolution);if(resolution===null)return
  if(!resolution.trim()){setError(L.resolution);return}
  update(ticket,{status:'resolved',resolution:resolution.trim()})
 }
 return <div className="acc-stack">
  <Card title={L.support} actions={<div className="row-actions"><select value={filters.status} onChange={event=>setFilters({...filters,status:event.target.value})}><option value="">{L.filterAll}</option>{['open','in_review','resolved'].map(value=><option key={value} value={value}>{L[value]||value}</option>)}</select><select value={filters.priority} onChange={event=>setFilters({...filters,priority:event.target.value})}><option value="">{L.priority} · {L.all}</option>{['low','normal','high'].map(value=><option key={value} value={value}>{value}</option>)}</select><select value={filters.assigned} onChange={event=>setFilters({...filters,assigned:event.target.value})}><option value="">{L.agent} · {L.all}</option><option value="me">{L.assignedTo}: {L.agent}</option><option value="unassigned">{L.unassigned}</option></select></div>}>
   <ErrorBox text={resource.error||error}/>
   {!data&&!resource.error&&<Loader/>}
   {data&&<><div className="acc-kpis"><KPI label={L.openTickets} value={data.counts.open} icon="support"/><KPI label={L.review} value={data.counts.in_review} icon="chart"/><KPI label={L.completed} value={data.counts.resolved} icon="orders"/><KPI label={L.avgRating} value={(data.ratings[0]?.average??0).toFixed?.(2)||'—'} icon="chart"/></div>
   <div className="table-wrap"><table><thead><tr><th>{L.ticket}</th><th>{L.priority}</th><th>{L.status}</th><th>{L.customer}</th><th>{L.assignedTo}</th><th/></tr></thead><tbody>{data.tickets.map(ticket=><tr key={ticket.id}><td><b>{ticket.subject}</b><small className="acc-sub">#{ticket.id} · {ticket.category}{ticket.order_number?` · ${ticket.order_number}`:''}</small><p className="muted-note">{ticket.message}</p>{ticket.resolution&&<small className="acc-sub">{L.resolution}: {ticket.resolution}</small>}</td><td>{ticket.priority}</td><td><Status value={ticket.status} labels={L}/></td><td>{ticket.user_name}</td><td><select value={ticket.assigned_to||''} disabled={busy===`t-${ticket.id}`} onChange={event=>update(ticket,{assigned_to:event.target.value?Number(event.target.value):null})}><option value="">{L.unassigned}</option>{data.agents.map(agent=><option key={agent.id} value={agent.id}>{agent.first_name||agent.username}</option>)}</select></td><td><div className="row-actions">{ticket.status!=='resolved'&&<button type="button" onClick={()=>resolve(ticket)}>{L.resolve}</button>}<select value={ticket.status} onChange={event=>update(ticket,{status:event.target.value})}>{['open','in_review','resolved'].map(value=><option key={value} value={value}>{L[value]||value}</option>)}</select></div></td></tr>)}</tbody></table></div></>}
  </Card>
  {data&&<Card title={L.rating}><div className="acc-grid two"><div className="table-wrap"><table><thead><tr><th>{L.service}</th><th>{L.rating}</th></tr></thead><tbody>{data.ratings.map(row=><tr key={row.target_type}><td>{row.target_type}</td><td>{Number(row.average).toFixed(2)} ({row.total})</td></tr>)}</tbody></table></div><div>{data.recent_ratings.map(row=><div className="acc-row-line" key={row.id}><span>{row.comment||row.order_number}</span><b>{row.score}</b></div>)}{!data.recent_ratings.length&&<p className="muted-note">{L.empty}</p>}</div></div></Card>}
 </div>
}

export function AuditPanel({lang,L}){
 const [filters,setFilters]=useState({q:'',action:''})
 const resource=useResource(()=>api(`/admin/control/audit/?${new URLSearchParams(Object.entries(filters).filter(([,value])=>value)).toString()}`),[lang,filters])
 const data=resource.data
 return <div className="acc-stack"><Card title={L.audit} actions={<div className="row-actions"><div className="search-field"><input value={filters.q} onChange={event=>setFilters({...filters,q:event.target.value})} placeholder={L.search} aria-label={L.search}/></div><select value={filters.action} onChange={event=>setFilters({...filters,action:event.target.value})}><option value="">{L.action} · {L.all}</option>{(data?.actions||[]).map(action=><option key={action} value={action}>{action}</option>)}</select><button type="button" className="secondary" onClick={resource.reload}>{L.refresh}</button></div>}>
 <ErrorBox text={resource.error}/>
 {!data&&!resource.error&&<Loader/>}
 {data&&<div className="table-wrap"><table><thead><tr><th>{L.date}</th><th>{L.actor}</th><th>{L.action}</th><th>{L.target}</th><th>{L.details}</th></tr></thead><tbody>{data.entries.map(row=><tr key={row.id}><td>{when(row.created_at)}</td><td>{row.actor}</td><td>{row.action}</td><td>{row.target_type} #{row.target_id}</td><td><span>{row.summary}</span><details><summary>{L.before} / {L.after}</summary><pre className="acc-pre">{JSON.stringify({before:row.before,after:row.after},null,2)}</pre></details></td></tr>)}</tbody></table></div>}
 </Card></div>
}

export function AlertsPanel({lang,L}){
 const resource=useResource(()=>api('/admin/control/alerts/'),[lang])
 const data=resource.data
 return <div className="acc-stack"><Card title={L.notifications} actions={<button type="button" className="secondary" onClick={resource.reload}>{L.refresh}</button>}>
  <ErrorBox text={resource.error}/>
  {!data&&!resource.error&&<Loader/>}
  {data&&<div className="acc-grid three">{(Array.isArray(data.alerts)?data.alerts:[]).filter(alert=>alert&&typeof alert==='object').map(alert=><div className={`acc-alert-card ${alert.severity||'info'}`} key={alert.kind||String(Math.random())}><div className="acc-alert-head"><span>{alert.kind}</span><b>{alert.count??0}</b></div>{(Array.isArray(alert.samples)?alert.samples:[]).filter(sample=>sample&&typeof sample==='object').map((sample,index)=><small key={sample.id??index}>• {sample.label||''}</small>)}{!alert.count&&<small className="muted-note">{L.noAlerts}</small>}</div>)}{!Array.isArray(data.alerts)&&<p className="muted-note">{L.empty}</p>}</div>}
 </Card></div>
}

export function SettingsPanel({lang,L}){
 const resource=useResource(()=>api('/admin/control/settings/'),[lang])
 const [form,setForm]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[note,setNote]=useState('')
 useEffect(()=>{if(resource.data&&!form)setForm({...resource.data})},[resource.data])
 async function save(){
  setBusy(true);setError('');setNote('')
  try{await api('/admin/control/settings/',{method:'PATCH',body:JSON.stringify({default_delivery_fee:form.default_delivery_fee,default_commission_percent:form.default_commission_percent===''?null:form.default_commission_percent,currency:form.currency,support_email:form.support_email})});setNote(L.saved);resource.reload()}
  catch(err){setError(err.message)}finally{setBusy(false)}
 }
 return <div className="acc-stack"><Card title={L.settings} subtitle={L.settingsHint}>
  <ErrorBox text={resource.error||error}/>
  {!form?<Loader/>:<div className="acc-form-grid"><Field label={L.deliveryFee}>{<input type="number" min="0" step="0.01" value={form.default_delivery_fee} onChange={event=>setForm({...form,default_delivery_fee:event.target.value})}/>}</Field><Field label={L.defaultCommission} hint={form.commission_configured?undefined:L.noData}>{<input type="number" min="0" max="100" step="0.01" value={form.default_commission_percent??''} onChange={event=>setForm({...form,default_commission_percent:event.target.value})}/>}</Field><Field label={L.currency}>{<input value={form.currency} onChange={event=>setForm({...form,currency:event.target.value})}/>}</Field><Field label="Email">{<input type="email" value={form.support_email} onChange={event=>setForm({...form,support_email:event.target.value})}/>}</Field></div>}
  {form&&<div className="row-actions"><button type="button" disabled={busy} onClick={save}>{busy?L.loading:L.save}</button></div>}
  {note&&<p className="success-note">{note}</p>}
 </Card></div>
}
