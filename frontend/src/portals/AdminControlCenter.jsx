import {useEffect,useMemo,useState} from 'react'
import {Link,useNavigate,useParams} from 'react-router-dom'
import {api} from '../api'
import {Glyph,LABELS,Loader,ErrorBox} from './adminUi.jsx'
import Brand from '../components/Brand'
import {BranchesPanel,CaptainsPanel,OverviewPanel,ProvidersPanel,ServicesPanel} from './AdminPanelsCore.jsx'
import {ActivitiesPanel} from './AdminPanelsActivities.jsx'
import {AlertsPanel,AnalyticsPanel,AuditPanel,FinancePanel,MapPanel,OperationsPanel,SettingsPanel,StaffPanel,SupportPanel} from './AdminPanelsOps.jsx'

const SECTIONS=[
 ['overview','grid','dashboard'],
 ['services','layers','services'],
 ['business','grid','services'],
 ['providers','store','providers'],
 ['pharmacy_products','store','providers'],
 ['branches','pin','branches'],
 ['captains','scooter','captains'],
 ['operations','orders','operations'],
 ['map','map','map'],
 ['analytics','chart','analytics'],
 ['finance','money','finance'],
 ['staff','users','staff'],
 ['support','support','support'],
 ['audit','shield','audit'],
 ['notifications','bell','notifications'],
 ['settings','gear','settings'],
]

export default function AdminControlCenter({lang='ar'}){
 const L=LABELS[lang]||LABELS.ar
 const params=useParams()
 const navigate=useNavigate()
 const section=params.section||'overview'
 const [me,setMe]=useState(null),[meError,setMeError]=useState('')
 const [alerts,setAlerts]=useState(0)
 useEffect(()=>{let live=true;api('/admin/control/me/').then(row=>{if(live){setMe(row);setMeError('')}}).catch(err=>{if(live)setMeError(err.message)});return()=>{live=false}},[lang])
 useEffect(()=>{let live=true;api('/admin/control/alerts/').then(row=>{if(live)setAlerts((row.alerts||[]).reduce((sum,alert)=>sum+(alert.count||0),0))}).catch(()=>{});return()=>{live=false}},[lang,section])
 const allowed=useMemo(()=>{
  if(!me)return []
  return SECTIONS.filter(([, , permission])=>me.permissions.includes(permission))
 },[me])

 if(meError)return <div className="acc-shell"><div className="acc-main"><ErrorBox text={`${L.error}: ${meError}`}/></div></div>
 if(!me)return <div className="acc-shell"><div className="acc-main"><Loader/></div></div>

 const visible=allowed.length?allowed:SECTIONS.slice(0,1)
 const current=visible.find(([key])=>key===section)?section:visible[0][0]
 const go=key=>navigate(`/admin/${key==='overview'?'':key}`.replace(/\/$/,'')||'/admin')
 const panel=(()=>{
  switch(current){
   case 'services':return <ServicesPanel lang={lang} L={L}/>
   case 'business':return <ActivitiesPanel lang={lang} L={L}/>
   case 'providers':return <ProvidersPanel lang={lang} L={L}/>
   case 'pharmacy_products':return <PharmacyProductsPanel lang={lang} L={L}/>
   case 'branches':return <BranchesPanel lang={lang} L={L}/>
   case 'captains':return <CaptainsPanel lang={lang} L={L}/>
   case 'operations':return <OperationsPanel lang={lang} L={L}/>
   case 'map':return <MapPanel lang={lang} L={L}/>
   case 'analytics':return <AnalyticsPanel lang={lang} L={L}/>
   case 'finance':return <FinancePanel lang={lang} L={L}/>
   case 'staff':return <StaffPanel lang={lang} L={L}/>
   case 'support':return <SupportPanel lang={lang} L={L}/>
   case 'audit':return <AuditPanel lang={lang} L={L}/>
   case 'notifications':return <AlertsPanel lang={lang} L={L}/>
   case 'settings':return <SettingsPanel lang={lang} L={L}/>
   default:return <OverviewPanel lang={lang} L={L} onGo={go}/>
  }
 })()
 return <div className="acc-shell">
  <nav className="acc-nav" aria-label={L.title}>
   <div className="acc-nav-head"><Brand name="" size="sm" /><div><b>{L.title}</b><small>{me.role_label}</small></div></div>
   <div className="acc-nav-links">
    {visible.map(([key,icon])=><button type="button" key={key} className={current===key?'is-active':''} onClick={()=>go(key)}><Glyph name={icon} size={17}/><span>{key==='pharmacy_products'?(lang==='en'?'Pharmacy review':lang==='he'?'בדיקת מוצרים':'مراجعة منتجات الصيدليات'):L[key]}</span>{key==='notifications'&&alerts>0&&<b className="acc-badge">{alerts}</b>}</button>)}
   </div>
   <Link className="acc-nav-legacy" to="/admin/legacy"><Glyph name="logout" size={16}/><span>{L.legacy}</span></Link>
  </nav>
  <main className="acc-main">
   <header className="acc-header"><div><small className="eyebrow">WASELNI ADMIN · {me.role_label}</small><h2>{current==='pharmacy_products'?(lang==='en'?'Pharmacy product review':lang==='he'?'בדיקת מוצרי בית מרקחת':'مراجعة منتجات الصيدليات'):L[current]||L.title}</h2><p>{L.subtitle}</p></div><div className="header-actions"><Link className="button-like secondary" to="/admin/legacy">{L.legacy}</Link></div></header>
   {panel}
  </main>
 </div>
}

function PharmacyProductsPanel({lang,L}){
 const words=lang==='en'?{hint:'Only approved, non-prescription products are visible to customers.',merchant:'Pharmacy',prescription:'Prescription required',controlled:'Controlled',approve:'Approve for sale',reject:'Reject',status:'Review status'}:
  lang==='he'?{hint:'רק מוצרים מאושרים ללא מרשם מוצגים ללקוחות.',merchant:'בית מרקחת',prescription:'נדרש מרשם',controlled:'תרופה בפיקוח',approve:'אישור למכירה',reject:'דחייה',status:'מצב בדיקה'}:
  {hint:'لا تظهر للزبائن إلا المنتجات المعتمدة التي لا تتطلب وصفة وليست مقيدة.',merchant:'الصيدلية',prescription:'يتطلب وصفة',controlled:'دواء مقيد',approve:'اعتماد للبيع',reject:'رفض',status:'حالة المراجعة'};
 const [rows,setRows]=useState([]),[error,setError]=useState(''),[busy,setBusy]=useState(null);
 async function load(){try{setRows(await api('/admin/control/pharmacy-products/'));setError('')}catch(e){setError(e.message)}}
 useEffect(()=>{load()},[]);
 async function review(row,status){setBusy(row.id);setError('');try{await api(`/admin/control/pharmacy-products/${row.id}/`,{method:'PATCH',body:JSON.stringify({status})});await load()}catch(e){setError(e.message)}finally{setBusy(null)}}
 return <section className="panel"><div className="section-head"><div><h3>{lang==='en'?'Pharmacy product review':lang==='he'?'בדיקת מוצרי בית מרקחת':'مراجعة منتجات الصيدليات'}</h3><p>{words.hint}</p></div><button className="secondary" onClick={load}>{L.refresh}</button></div>
  {error&&<p className="error">{error}</p>}
  <div className="table-wrap"><table><thead><tr><th>{L.name}</th><th>{words.merchant}</th><th>{L.category}</th><th>{words.prescription}</th><th>{words.controlled}</th><th>{words.status}</th><th/></tr></thead>
   <tbody>{rows.map(row=><tr key={row.id}><td>{row.name}</td><td>{row.merchant_name}</td><td>{row.category||'—'}</td><td>{row.prescription_required?L.yes||'Yes':'—'}</td><td>{row.controlled_substance?L.yes||'Yes':'—'}</td><td>{L[row.review_status]||row.review_status}</td><td className="row-actions">{row.review_status==='pending'&&<><button disabled={busy===row.id} onClick={()=>review(row,'approved')}>{words.approve}</button><button className="secondary danger" disabled={busy===row.id} onClick={()=>review(row,'rejected')}>{words.reject}</button></>}</td></tr>)}
   {!rows.length&&<tr><td colSpan="7">{L.empty}</td></tr>}</tbody></table></div>
 </section>
}
