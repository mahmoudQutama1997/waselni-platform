import {useEffect,useMemo,useState} from 'react'
import {Link,useNavigate,useParams} from 'react-router-dom'
import {api} from '../api'
import {Glyph,LABELS,Loader,ErrorBox} from './adminUi.jsx'
import {BranchesPanel,CaptainsPanel,OverviewPanel,ProvidersPanel,ServicesPanel} from './AdminPanelsCore.jsx'
import {ActivitiesPanel} from './AdminPanelsActivities.jsx'
import {AlertsPanel,AnalyticsPanel,AuditPanel,FinancePanel,MapPanel,OperationsPanel,SettingsPanel,StaffPanel,SupportPanel} from './AdminPanelsOps.jsx'

const SECTIONS=[
 ['overview','grid','dashboard'],
 ['services','layers','services'],
 ['business','grid','services'],
 ['providers','store','providers'],
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
   <div className="acc-nav-head"><span className="brand-mark small">و</span><div><b>{L.title}</b><small>{me.role_label}</small></div></div>
   <div className="acc-nav-links">
    {visible.map(([key,icon])=><button type="button" key={key} className={current===key?'is-active':''} onClick={()=>go(key)}><Glyph name={icon} size={17}/><span>{L[key]}</span>{key==='notifications'&&alerts>0&&<b className="acc-badge">{alerts}</b>}</button>)}
   </div>
   <Link className="acc-nav-legacy" to="/admin/legacy"><Glyph name="logout" size={16}/><span>{L.legacy}</span></Link>
  </nav>
  <main className="acc-main">
   <header className="acc-header"><div><small className="eyebrow">WASELNI ADMIN · {me.role_label}</small><h2>{L[current]||L.title}</h2><p>{L.subtitle}</p></div><div className="header-actions"><Link className="button-like secondary" to="/admin/legacy">{L.legacy}</Link></div></header>
   {panel}
  </main>
 </div>
}
