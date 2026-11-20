import {useEffect,useState} from 'react'
import {api} from '../api'
import {Card,Empty,ErrorBox,Field,Glyph,KPI,Loader,Status,money,useResource,when} from './adminUi.jsx'

const labelOf=(rows,code)=>rows?.find(row=>row.code===code)?.label||code||'—'

export function OverviewPanel({lang,L,onGo}){
 const analytics=useResource(()=>api('/admin/control/analytics/?days=7'),[lang])
 const alerts=useResource(()=>api('/admin/control/alerts/'),[lang])
 const operations=useResource(()=>api('/admin/control/operations/?status=active&limit=6'),[lang])
 const data=analytics.data
 return <div className="acc-stack">
  <ErrorBox text={analytics.error||alerts.error||operations.error}/>
  {!data&&!analytics.error&&<Loader/>}
  {data&&<div className="acc-kpis">
   <KPI label={L.totalOrders} value={data.orders.total} icon="orders"/>
   <KPI label={L.activeOrders} value={data.orders.active} icon="map" tone="accent"/>
   <KPI label={L.sales} value={money(data.money.sales)} icon="money"/>
   <KPI label={L.captainsOnline} value={data.people.captains_online} icon="scooter"/>
   <KPI label={L.merchants} value={data.people.merchants} icon="store"/>
   <KPI label={L.pending} value={data.people.pending_merchants} icon="shield" tone={data.people.pending_merchants?'warn':''}/>
   <KPI label={L.cancelRate} value={`${data.orders.cancellation_rate}%`} icon="chart"/>
   <KPI label={L.avgMinutes} value={data.orders.average_completion_minutes??'—'} icon="chart"/>
  </div>}
  <div className="acc-grid two">
   <Card title={L.ordersSeries} subtitle={L.refreshHint}>
    {data?<div className="acc-bars">{data.series.map(day=><div className="acc-bar" key={day.date} title={`${day.date}: ${day.orders}`}><b>{day.orders}</b><div className="acc-bar-track"><i style={{height:`${Math.max(4,(day.orders/Math.max(1,...data.series.map(d=>d.orders)))*100)}%`}}/></div><small>{day.date.slice(5)}</small></div>)}</div>:<Loader/>}
   </Card>
   <Card title={L.notifications} subtitle={L.noAlerts}>
    {alerts.data?<div className="acc-alerts">{alerts.data.alerts.map(alert=><button type="button" className={`acc-alert ${alert.severity}`} key={alert.kind} onClick={()=>onGo(alert.kind==='merchant_application'||alert.kind==='captain_application'?(alert.kind==='captain_application'?'captains':'providers'):alert.kind==='open_ticket'||alert.kind==='delivery_issue'?'support':alert.kind==='pending_settlement'?'finance':alert.kind==='low_stock'?'services':'operations')}><span>{alert.kind}</span><b>{alert.count}</b></button>)}{!alerts.data.alerts.some(a=>a.count)&&<p className="muted-note">{L.noAlerts}</p>}</div>:<Loader/>}
   </Card>
  </div>
  <Card title={L.operations} actions={<button type="button" className="secondary" onClick={()=>onGo('operations')}>{L.details}</button>}>
   {operations.data?<div className="table-wrap"><table><thead><tr><th>{L.orders}</th><th>{L.service}</th><th>{L.status}</th><th>{L.customer}</th><th>{L.total}</th><th>{L.date}</th></tr></thead><tbody>{operations.data.orders.map(order=><tr key={order.id}><td>{order.order_number}</td><td>{order.service_type}</td><td><Status value={order.status} labels={L}/></td><td>{order.customer_name}</td><td>{money(order.total)}</td><td>{when(order.created_at)}</td></tr>)}</tbody></table></div>:<Loader/>}
  </Card>
 </div>
}

const BLANK={code:'',name_ar:'',name_en:'',name_he:'',description_ar:'',description_en:'',category:'food_trade',business_type:'merchant',workflow:'merchant_accept',pricing_mode:'fixed',requires_merchant:true,requires_captain:true,requires_specialist:false,requires_booking:false,provider_requirements:'',order_flow:'',working_hours:[],regions:[],fulfilment_service:'',sort_order:100,is_active:false,icon:''}

export function ServicesPanel({lang,L}){
 const resource=useResource(()=>api('/admin/control/services/'),[lang])
 const [form,setForm]=useState(null),[busy,setBusy]=useState(false),[note,setNote]=useState(''),[error,setError]=useState('')
 const [query,setQuery]=useState('')
 const meta=resource.data
 function startCreate(){setForm({...BLANK})}
 function startEdit(service){setForm({...service,order_flow:(service.order_flow||[]).join(','),regions:(service.regions||[]).map(r=>r.id),fulfilment_service:service.fulfilment_service?.id||''})}
 function field(key,value){setForm(current=>({...current,[key]:value}))}
 async function save(){
  if(!form)return;setBusy(true);setError('');setNote('')
  const payload={...form,fulfilment_service:form.fulfilment_service||null,order_flow:form.order_flow?String(form.order_flow).split(',').map(x=>x.trim()).filter(Boolean):[],working_hours:form.working_hours||[],regions:form.regions||[]}
  if(form.id){delete payload.id;delete payload.captains_count;delete payload.merchants_count;delete payload.branches_count;delete payload.active_orders;delete payload.implemented;delete payload.updated_at;delete payload.image;delete payload.activities;delete payload.activities_count;delete payload.effective_code;delete payload.runs_order_flow}
  try{
   if(form.id)await api(`/admin/control/services/${form.id}/`,{method:'PATCH',body:JSON.stringify(payload)})
   else await api('/admin/control/services/',{method:'POST',body:JSON.stringify(payload)})
   setNote(L.saved);setForm(null);resource.reload()
  }catch(err){setError(err.message)}finally{setBusy(false)}
 }
 async function toggle(service){
  setBusy(true);setError('')
  try{await api(`/admin/control/services/${service.id}/`,{method:'PATCH',body:JSON.stringify({is_active:!service.is_active})});resource.reload()}
  catch(err){setError(err.message)}finally{setBusy(false)}
 }
 const rows=(meta?.services||[]).filter(row=>!query.trim()||`${row.code} ${row.name_ar} ${row.name_en}`.toLowerCase().includes(query.trim().toLowerCase()))
 const activeCount=(meta?.services||[]).filter(row=>row.is_active).length
 const stoppedCount=(meta?.services?.length||0)-activeCount
 return <div className="acc-stack">
  <Card title={L.services} subtitle={L.servicesHint} actions={<div className="row-actions"><button type="button" onClick={startCreate}>{L.addService}</button></div>}>
   <div className="table-toolbar"><div className="search-field"><span aria-hidden="true">⌕</span><input value={query} onChange={event=>setQuery(event.target.value)} placeholder={L.search} aria-label={L.search}/></div><span className="muted-note">{rows.length} / {meta?.services?.length||0} · {activeCount} {L.activeServices} · {stoppedCount} {L.stoppedServices}</span></div>
   <ErrorBox text={resource.error||error}/>
   {meta?.operational_codes&&<p className="muted-note">{L.orderFlowHint}: {meta.operational_codes.join(', ')}</p>}
   {!meta&&!resource.error&&<Loader/>}
   {meta&&<div className="table-wrap"><table><thead><tr><th>{L.name}</th><th>{L.category}</th><th>{L.workflow}</th><th>{L.pricing}</th><th>{L.servicesLinked}</th><th>{L.linkedActivities}</th><th>{L.status}</th><th/></tr></thead><tbody>{rows.map(service=><tr key={service.id}><td><b>{lang==='ar'?service.name_ar:service.name_en}</b><small className="acc-sub">{service.code} · {lang==='ar'?service.name_en:service.name_ar}</small></td><td>{labelOf(meta.categories,service.category)}</td><td>{labelOf(meta.workflows,service.workflow)}</td><td>{labelOf(meta.pricing_modes,service.pricing_mode)}</td><td><small>{service.merchants_count} {L.merchantsCount} · {service.captains_count} {L.captainsCount} · {service.active_orders} {L.serviceOrders}</small></td><td><small>{(service.activities||[]).map(row=>lang==='ar'?row.name_ar:row.name_en).join(' · ')||'—'}</small><small className="acc-sub">{service.effective_code&&service.effective_code!==service.code?`${L.effectiveService}: ${service.effective_code}`:service.runs_order_flow?'':L.serviceFlowMissing}</small></td><td>{service.is_active?<Status value="active" labels={L}/>:<Status value="inactive" labels={L}/>}</td><td><div className="row-actions"><button type="button" className="secondary" onClick={()=>startEdit(service)}>{L.edit}</button><button type="button" className="secondary" disabled={busy} onClick={()=>toggle(service)}>{service.is_active?L.disable:L.enable}</button></div></td></tr>)}</tbody></table></div>}
   {note&&<p className="success-note">{note}</p>}
  </Card>
  {form&&<Card title={form.id?L.editService:L.addService} actions={<button type="button" className="ghost" onClick={()=>setForm(null)}>{L.close}</button>}>
   <div className="acc-form-grid">
    <Field label={L.code} hint="flowers">{<input value={form.code} disabled={!!form.id} onChange={event=>field('code',event.target.value)} placeholder="flowers"/>}</Field>
    <Field label={L.nameAr}>{<input value={form.name_ar} onChange={event=>field('name_ar',event.target.value)}/>}</Field>
    <Field label={L.nameEn}>{<input value={form.name_en} onChange={event=>field('name_en',event.target.value)}/>}</Field>
    <Field label={L.descriptionAr}><textarea rows={2} value={form.description_ar||''} onChange={event=>field('description_ar',event.target.value)}/></Field>
    <Field label={L.descriptionEn}><textarea rows={2} value={form.description_en||''} onChange={event=>field('description_en',event.target.value)}/></Field>
    <Field label={L.fulfilmentService} hint={L.fulfilmentServiceHint}>{<select value={form.fulfilment_service||''} onChange={event=>field('fulfilment_service',event.target.value)}><option value="">—</option>{(meta?.services||[]).filter(row=>row.is_operational&&row.id!==form.id).map(row=><option key={row.id} value={row.id}>{lang==='ar'?row.name_ar:row.name_en}</option>)}</select>}</Field>
    <Field label={L.category}>{<select value={form.category} onChange={event=>field('category',event.target.value)}>{meta?.categories.map(row=><option key={row.code} value={row.code}>{row.label}</option>)}</select>}</Field>
    <Field label={L.businessType}>{<select value={form.business_type} onChange={event=>field('business_type',event.target.value)}>{meta?.business_types.map(row=><option key={row.code} value={row.code}>{row.label}</option>)}</select>}</Field>
    <Field label={L.workflow}>{<select value={form.workflow} onChange={event=>field('workflow',event.target.value)}>{meta?.workflows.map(row=><option key={row.code} value={row.code}>{row.label}</option>)}</select>}</Field>
    <Field label={L.pricing}>{<select value={form.pricing_mode} onChange={event=>field('pricing_mode',event.target.value)}>{meta?.pricing_modes.map(row=><option key={row.code} value={row.code}>{row.label}</option>)}</select>}</Field>
    <Field label={L.flow} hint={L.orderFlowHint}>{<input value={form.order_flow} onChange={event=>field('order_flow',event.target.value)} placeholder="new,accepted,preparing,ready,completed"/>}</Field>
    <Field label={L.requirements}>{<textarea rows={2} value={form.provider_requirements} onChange={event=>field('provider_requirements',event.target.value)}/>}</Field>
    <div className="acc-checks">
     <label><input type="checkbox" checked={form.requires_merchant} onChange={event=>field('requires_merchant',event.target.checked)}/>{L.provider}</label>
     <label><input type="checkbox" checked={form.requires_captain} onChange={event=>field('requires_captain',event.target.checked)}/>{L.captain}</label>
     <label><input type="checkbox" checked={form.requires_specialist} onChange={event=>field('requires_specialist',event.target.checked)}/>{L.businessType}: specialist</label>
     <label><input type="checkbox" checked={form.requires_booking} onChange={event=>field('requires_booking',event.target.checked)}/>{L.hours}</label>
    </div>
    <Field label={L.regions}>{<div className="acc-checks">{meta?.regions.map(region=><label key={region.id}><input type="checkbox" checked={(form.regions||[]).includes(region.id)} onChange={event=>field('regions',event.target.checked?[...(form.regions||[]),region.id]:(form.regions||[]).filter(id=>id!==region.id))}/>{region.name_en}</label>)}{!meta?.regions.length&&<small>{L.empty}</small>}</div>}</Field>
    <Field label={L.active} hint={form.is_operational||form.fulfilment_service?'':L.serviceFlowMissing}>{<input type="checkbox" checked={!!form.is_active} onChange={event=>field('is_active',event.target.checked)}/>}</Field>
   </div>
   <ErrorBox text={error}/>
   <div className="row-actions"><button type="button" disabled={busy||!form.code||!form.name_ar||!form.name_en} onClick={save}>{busy?L.loading:L.save}</button><button type="button" className="secondary" onClick={()=>setForm(null)}>{L.cancel}</button></div>
  </Card>}
 </div>
}

export function ProvidersPanel({lang,L}){
 const [status,setStatus]=useState('')
 const resource=useResource(()=>api(`/admin/control/providers/${status?`?status=${status}`:''}`),[lang,status])
 const services=useResource(()=>api('/admin/control/services/'),[lang])
 const [busy,setBusy]=useState(''),[error,setError]=useState(''),[expanded,setExpanded]=useState(null)
 async function review(provider,next,reason=''){
  setBusy(`p-${provider.id}`);setError('')
  try{await api(`/admin/control/providers/${provider.id}/`,{method:'PATCH',body:JSON.stringify({approval_status:next,reason})});resource.reload()}
  catch(err){setError(err.message)}finally{setBusy('')}
 }
 async function saveServices(provider,ids){
  setBusy(`s-${provider.id}`);setError('')
  try{await api(`/admin/control/providers/${provider.id}/`,{method:'PATCH',body:JSON.stringify({services:ids})});resource.reload()}
  catch(err){setError(err.message)}finally{setBusy('')}
 }
 async function saveActivity(provider,categoryId){
  setBusy(`a-${provider.id}`);setError('')
  try{await api(`/admin/control/providers/${provider.id}/`,{method:'PATCH',body:JSON.stringify({business_category:categoryId||null})});resource.reload()}
  catch(err){setError(err.message)}finally{setBusy('')}
 }
 function askReason(provider,next){
  const reason=window.prompt(L.reason);if(reason===null)return
  if(!reason.trim()){setError(L.reason);return}
  review(provider,next,reason.trim())
 }
 return <div className="acc-stack">
  <Card title={L.providers} subtitle={`${resource.data?.providers?.length||0}`} actions={<div className="row-actions"><select value={status} onChange={event=>setStatus(event.target.value)}><option value="">{L.all}</option>{['pending','approved','suspended','rejected'].map(value=><option key={value} value={value}>{L[value]||value}</option>)}</select><button type="button" className="secondary" onClick={resource.reload}>{L.refresh}</button></div>}>
   <ErrorBox text={resource.error||error}/>
   {!resource.data&&!resource.error&&<Loader/>}
   {resource.data&&<div className="table-wrap"><table><thead><tr><th>{L.provider}</th><th>{L.category}</th><th>{L.status}</th><th>{L.sales}</th><th>{L.servicesLinked}</th><th/></tr></thead><tbody>{resource.data.providers.map(provider=><tr key={provider.id}><td><b>{provider.shop_name}</b><small className="acc-sub">{provider.owner_name} · {provider.username} · {provider.phone||'—'}</small><small className="acc-sub">{provider.address||'—'} · {provider.branch_count} {L.branchesCount}</small></td><td>{provider.business_category?(lang==='ar'?provider.business_category.name_ar:provider.business_category.name_en):provider.category}</td><td><Status value={provider.approval_status} labels={L}/>{provider.rejection_reason&&<small className="acc-sub">{provider.rejection_reason}</small>}</td><td>{money(provider.sales)}<small className="acc-sub">{provider.orders_completed} {L.orders}</small></td><td><small>{provider.services.length?provider.services.join(', '):'—'}</small><button type="button" className="link-button" onClick={()=>setExpanded(expanded===provider.id?null:provider.id)}>{L.edit}</button></td><td><div className="row-actions">{provider.approval_status!=='approved'&&<button type="button" disabled={busy===`p-${provider.id}`} onClick={()=>review(provider,'approved')}>{L.approve}</button>}{provider.approval_status==='approved'&&<button type="button" className="secondary" onClick={()=>askReason(provider,'suspended')}>{L.suspend}</button>}{provider.approval_status!=='rejected'&&<button type="button" className="secondary danger" onClick={()=>askReason(provider,'rejected')}>{L.reject}</button>}</div></td></tr>)}</tbody></table></div>}
   {expanded&&(()=>{const provider=resource.data?.providers.find(row=>row.id===expanded);if(!provider)return null;return <div className="acc-inline-editor"><b>{provider.shop_name} · {L.servicesLinked}</b><label className="acc-inline-field">{L.activity}<select value={provider.business_category?.id||''} disabled={busy===`a-${provider.id}`} onChange={event=>saveActivity(provider,event.target.value)}><option value="">{L.noService}</option>{(resource.data?.business_categories||[]).map(row=><option key={row.id} value={row.id}>{lang==='ar'?row.name_ar:row.name_en}</option>)}</select></label><div className="acc-checks">{(services.data?.services||[]).map(service=><label key={service.id}><input type="checkbox" defaultChecked={provider.services.includes(service.code)} onChange={event=>{const current=new Set(provider.services);if(event.target.checked)current.add(service.code);else current.delete(service.code);saveServices(provider,(services.data?.services||[]).filter(s=>current.has(s.code)).map(s=>s.id))}}/>{lang==='ar'?service.name_ar:service.name_en}</label>)}</div></div>})()}
  </Card>
 </div>
}

export function BranchesPanel({lang,L}){
 const resource=useResource(()=>api('/admin/control/branches/'),[lang])
 const services=useResource(()=>api('/admin/control/services/'),[lang])
 const [busy,setBusy]=useState(''),[error,setError]=useState(''),[region,setRegion]=useState({code:'',name_ar:'',name_en:'',radius_km:15})
 async function patch(branch,payload){
  setBusy(`b-${branch.id}`);setError('')
  try{await api(`/admin/control/branches/${branch.id}/`,{method:'PATCH',body:JSON.stringify(payload)});resource.reload()}
  catch(err){setError(err.message)}finally{setBusy('')}
 }
 async function createRegion(){
  setBusy('region');setError('')
  try{await api('/admin/control/regions/',{method:'POST',body:JSON.stringify(region)});setRegion({code:'',name_ar:'',name_en:'',radius_km:15});resource.reload()}
  catch(err){setError(err.message)}finally{setBusy('')}
 }
 return <div className="acc-stack">
  <Card title={L.branches} subtitle={L.addRegionHint} actions={<button type="button" className="secondary" onClick={resource.reload}>{L.refresh}</button>}>
   <ErrorBox text={resource.error||error}/>
   {!resource.data&&!resource.error&&<Loader/>}
   {resource.data&&<div className="table-wrap"><table><thead><tr><th>{L.branch}</th><th>{L.provider}</th><th>{L.region}</th><th>{L.address}</th><th>{L.orders}</th><th>{L.status}</th></tr></thead><tbody>{resource.data.branches.map(branch=><tr key={branch.id}><td><b>{branch.name}</b><small className="acc-sub">{branch.latitude??'—'}, {branch.longitude??'—'}</small></td><td>{branch.merchant}</td><td><select value={branch.region?.id||''} disabled={busy===`b-${branch.id}`} onChange={event=>patch(branch,{region:event.target.value?Number(event.target.value):null})}><option value="">—</option>{resource.data.regions.map(row=><option key={row.id} value={row.id}>{lang==='ar'?row.name_ar:row.name_en}</option>)}</select></td><td>{branch.address||'—'}</td><td>{branch.orders_count}</td><td><button type="button" className="secondary" disabled={busy===`b-${branch.id}`} onClick={()=>patch(branch,{is_active:!branch.is_active})}>{branch.is_active?L.active:L.inactive}</button></td></tr>)}</tbody></table></div>}
  </Card>
  <div className="acc-grid two">
   <Card title={L.regions}>
    <ErrorBox text={services.error}/>
    {resource.data?<div className="table-wrap"><table><thead><tr><th>{L.name}</th><th>{L.radius}</th><th>{L.branchesCount}</th><th>{L.status}</th></tr></thead><tbody>{resource.data.regions.map(row=><tr key={row.id}><td>{lang==='ar'?row.name_ar:row.name_en}<small className="acc-sub">{row.code}</small></td><td>{row.radius_km}</td><td>{row.branches_count}</td><td><Status value={row.is_active?'active':'inactive'} labels={L}/></td></tr>)}</tbody></table></div>:<Loader/>}
   </Card>
   <Card title={L.addRegion}>
    <div className="acc-form-grid">
     <Field label={L.code}>{<input value={region.code} onChange={event=>setRegion({...region,code:event.target.value})} placeholder="ramallah"/>}</Field>
     <Field label={L.nameAr}>{<input value={region.name_ar} onChange={event=>setRegion({...region,name_ar:event.target.value})}/>}</Field>
     <Field label={L.nameEn}>{<input value={region.name_en} onChange={event=>setRegion({...region,name_en:event.target.value})}/>}</Field>
     <Field label={L.radius}>{<input type="number" min="1" max="300" value={region.radius_km} onChange={event=>setRegion({...region,radius_km:Number(event.target.value)})}/>}</Field>
    </div>
    <button type="button" disabled={busy==='region'||!region.code||!region.name_ar||!region.name_en} onClick={createRegion}>{busy==='region'?L.loading:L.addRegion}</button>
   </Card>
  </div>
  {services.data&&<Card title={`${L.services} · ${L.provider}`} subtitle={L.servicesHint}>{services.data.services.map(service=><div key={service.id} className="acc-row-line"><span>{lang==='ar'?service.name_ar:service.name_en}</span><small>{service.regions.map(r=>r.code).join(', ')||'—'}</small></div>)}</Card>}
 </div>
}

export function CaptainsPanel({lang,L}){
 const resource=useResource(()=>api('/admin/operations/'),[lang])
 const services=useResource(()=>api('/admin/control/services/'),[lang])
 const [open,setOpen]=useState(null),[detail,setDetail]=useState(null),[busy,setBusy]=useState(''),[error,setError]=useState('')
 useEffect(()=>{if(!open){setDetail(null);return}let live=true;api(`/admin/captains/${open}/services/`).then(rows=>{if(live)setDetail(rows)}).catch(err=>{if(live)setError(err.message)});return()=>{live=false}},[open])
 async function setService(service,status){
  setBusy(`${open}-${service}`);setError('')
  try{await api(`/admin/captains/${open}/services/`,{method:'POST',body:JSON.stringify({service,status})});const rows=await api(`/admin/captains/${open}/services/`);setDetail(rows);resource.reload()}
  catch(err){setError(err.message)}finally{setBusy('')}
 }
 async function setApproval(captain,status){
  const reason=window.prompt(L.reason);if(reason===null)return
  if(!reason.trim()){setError(L.reason);return}
  setBusy(`a-${captain.captain_profile_id}`);setError('')
  try{await api(`/admin/captains/${captain.captain_profile_id}/approval/`,{method:'POST',body:JSON.stringify({status,reason:reason.trim()})});resource.reload()}
  catch(err){setError(err.message)}finally{setBusy('')}
 }
 const operational=(services.data?.services||[]).filter(row=>row.implemented)
 return <div className="acc-stack">
  <Card title={L.captains} subtitle={`${resource.data?.captains?.length||0}`} actions={<button type="button" className="secondary" onClick={resource.reload}>{L.refresh}</button>}>
   <ErrorBox text={resource.error||error}/>
   {!resource.data&&!resource.error&&<Loader/>}
   {resource.data&&<div className="table-wrap"><table><thead><tr><th>{L.captain}</th><th>{L.status}</th><th>{L.captainServices}</th><th>{L.rating}</th><th/></tr></thead><tbody>{resource.data.captains.map(captain=>{const approval=captain.eligibility?.approval?.status||'pending';const approved=(captain.eligibility?.services||[]).filter(row=>row.status==='approved').map(row=>row.service);return <tr key={captain.captain_profile_id}><td><b>{captain.name}</b><small className="acc-sub">{captain.username} · {captain.vehicle_type} · {L.rating}: {captain.rating}</small></td><td><Status value={approval} labels={L}/><small className="acc-sub">{captain.online?'online':'offline'}</small></td><td><small>{approved.join(', ')||'—'}</small><button type="button" className="link-button" onClick={()=>setOpen(open===captain.captain_profile_id?null:captain.captain_profile_id)}>{L.edit}</button></td><td>{captain.rating}</td><td><div className="row-actions">{approval!=='approved'&&<button type="button" disabled={busy===`a-${captain.captain_profile_id}`} onClick={()=>setApproval(captain,'approved')}>{L.approve}</button>}{approval==='approved'&&<button type="button" className="secondary" onClick={()=>setApproval(captain,'pending')}>{L.suspend}</button>}</div></td></tr>})}</tbody></table></div>}
  </Card>
  {open&&<Card title={`${L.captainServices} · #${open}`} actions={<button type="button" className="ghost" onClick={()=>setOpen(null)}>{L.close}</button>}>
   <ErrorBox text={error}/>
   {!detail?<Loader/>:<div className="acc-service-matrix">{operational.map(service=>{const row=(detail.services||[]).find(item=>item.service===service.code);const status=row?.status||'none';return <div className="acc-row-line" key={service.code}><span>{lang==='ar'?service.name_ar:service.name_en}</span><small>{row?.regions?.join(', ')||'—'}</small><div className="row-actions"><Status value={status==='none'?'pending':status} labels={L}/><button type="button" className="secondary" disabled={busy===`${open}-${service.code}`} onClick={()=>setService(service.code,'approved')}>{L.approve}</button><button type="button" className="secondary" disabled={busy===`${open}-${service.code}`} onClick={()=>setService(service.code,'suspended')}>{L.suspend}</button></div></div>})}</div>}
  </Card>}
 </div>
}
