import {useState} from 'react'
import {api} from '../api'
import {Card,ErrorBox,Field,Loader,Status,useResource} from './adminUi.jsx'

const BLANK={code:'',name_ar:'',name_en:'',service:'',requires_license:false,is_active:true,sort_order:100}

/** Administrator-managed business activities and the service each one maps to. */
export function ActivitiesPanel({lang,L}){
 const resource=useResource(()=>api('/admin/control/business-categories/'),[lang])
 const [form,setForm]=useState(null),[busy,setBusy]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState('')
 const rows=resource.data?.categories||[],services=resource.data?.services||[]
 function field(key,value){setForm(current=>({...current,[key]:value}))}
 async function save(event){
  event.preventDefault();setBusy('save');setError('');setNotice('')
  const payload={
   name_ar:form.name_ar,name_en:form.name_en,service:form.service||null,
   requires_license:!!form.requires_license,is_active:!!form.is_active,
   sort_order:Number(form.sort_order)||100,
  }
  try{
   if(form.id)await api(`/admin/control/business-categories/${form.id}/`,{method:'PATCH',body:JSON.stringify(payload)})
   else await api('/admin/control/business-categories/',{method:'POST',body:JSON.stringify({...payload,code:form.code})})
   setForm(null);setNotice(L.activitySaved);resource.reload()
  }catch(err){setError(err.message)}finally{setBusy('')}
 }
 async function toggle(row){
  setBusy(`t-${row.id}`);setError('')
  try{await api(`/admin/control/business-categories/${row.id}/`,{method:'PATCH',body:JSON.stringify({is_active:!row.is_active})});resource.reload()}
  catch(err){setError(err.message)}finally{setBusy('')}
 }
 return <div className="acc-stack">
  <Card title={L.activitiesTitle} subtitle={L.activitiesHint} actions={<div className="row-actions"><button type="button" onClick={()=>{setNotice('');setForm({...BLANK})}}>{L.addActivity}</button><button type="button" className="secondary" onClick={resource.reload}>{L.refresh}</button></div>}>
   <ErrorBox text={resource.error||error}/>
   {notice&&<p className="success-note">{notice}</p>}
   {form&&<form className="acc-form" onSubmit={save}>
    <Field label={L.nameAr}><input value={form.name_ar} onChange={event=>field('name_ar',event.target.value)} required/></Field>
    <Field label={L.nameEn}><input value={form.name_en} onChange={event=>field('name_en',event.target.value)} required/></Field>
    {!form.id&&<Field label={L.code} hint="lowercase_letters"><input value={form.code} onChange={event=>field('code',event.target.value.toLowerCase())} pattern="[a-z][a-z0-9_]{1,39}" required/></Field>}
    <Field label={L.linkedService}>
     <select value={form.service||''} onChange={event=>field('service',event.target.value)}>
      <option value="">{L.noService}</option>
      {services.map(service=><option key={service.id} value={service.id}>{lang==='ar'?service.name_ar:service.name_en}</option>)}
     </select>
    </Field>
    <Field label={L.sortOrderLabel||L.priority}><input type="number" min="0" value={form.sort_order} onChange={event=>field('sort_order',event.target.value)}/></Field>
    <label className="acc-check"><input type="checkbox" checked={!!form.requires_license} onChange={event=>field('requires_license',event.target.checked)}/>{L.requiresLicense}</label>
    <label className="acc-check"><input type="checkbox" checked={!!form.is_active} onChange={event=>field('is_active',event.target.checked)}/>{L.active}</label>
    <div className="row-actions"><button type="submit" disabled={busy==='save'}>{busy==='save'?L.loading:L.save}</button><button type="button" className="secondary" onClick={()=>setForm(null)}>{L.cancel}</button></div>
   </form>}
   {!resource.data&&!resource.error&&<Loader/>}
   {resource.data&&<div className="table-wrap"><table>
    <thead><tr><th>{L.name}</th><th>{L.code}</th><th>{L.linkedService}</th><th>{L.merchantsCount}</th><th>{L.status}</th><th/></tr></thead>
    <tbody>{rows.map(row=><tr key={row.id}>
     <td><b>{lang==='ar'?row.name_ar:row.name_en}</b><small className="acc-sub">{lang==='ar'?row.name_en:row.name_ar}{row.requires_license?` · ${L.requiresLicense}`:''}</small></td>
     <td><code>{row.code}</code></td>
     <td>{row.service?(lang==='ar'?row.service.name_ar:row.service.name_en):<span className="muted-note">{L.noService}</span>}<small className="acc-sub">{row.service?.code||''}</small></td>
     <td>{row.merchants_count??0}</td>
     <td><Status value={row.is_active?'active':'inactive'} labels={L}/></td>
     <td><div className="row-actions"><button type="button" className="secondary" onClick={()=>{setNotice('');setForm({...row,service:row.service_id||''})}}>{L.edit}</button><button type="button" className="secondary" disabled={busy===`t-${row.id}`} onClick={()=>toggle(row)}>{row.is_active?L.disable:L.enable}</button></div></td>
    </tr>)}</tbody>
   </table></div>}
  </Card>
 </div>
}
