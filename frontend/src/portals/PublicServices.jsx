import {useEffect,useState} from 'react'
import {Link} from 'react-router-dom'
import {api} from '../api'

const WORDS={
 ar:{title:'خدمات وصلني',empty:'لا توجد خدمات متاحة في منطقتك حالياً',loading:'جارٍ تحميل الخدمات…',error:'تعذر تحميل الخدمات',open:'استكشف الخدمة'},
 en:{title:'Waselni services',empty:'No services are available in your area yet',loading:'Loading services…',error:'Could not load services',open:'Explore service'},
 he:{title:'שירותי Waselni',empty:'אין שירותים זמינים באזורך כעת',loading:'טוען שירותים…',error:'לא ניתן לטעון שירותים',open:'לצפייה בשירות'},
}
const ROUTES={food:'/service/food',grocery:'/service/grocery',pharmacy:'/service/pharmacy',parcel:'/service/parcel',ride:'/ride',logistics:'/service/logistics'}

/** Customer-facing directory of services the administration has switched on. */
export default function PublicServices({lang='ar'}){
 const words=WORDS[lang]||WORDS.ar
 const [services,setServices]=useState(null),[error,setError]=useState('')
 useEffect(()=>{let live=true;api(`/services/?lang=${lang}`).then(rows=>{if(live)setServices(Array.isArray(rows)?rows:[])}).catch(err=>{if(live)setError(err.message)});return()=>{live=false}},[lang])
 if(!services&&!error)return <section className="panel public-services" aria-label={words.title}><p>{words.loading}</p></section>
 return <section className="panel public-services" aria-label={words.title}>
  <div className="section-head"><div><h3>{words.title}</h3></div><span className="count-pill">{services?.length||0}</span></div>
  {error?<p className="error">{words.error}: {error}</p>:services?.length?
   <div className="public-services-grid">{services.filter(service=>ROUTES[service.code]).map(service=><Link key={service.code} to={ROUTES[service.code]} className="public-service">
    <span className="feature-icon">{service.icon?<span aria-hidden="true">{service.icon}</span>:'✦'}</span><div><b>{service.name}</b>{service.description&&<small>{service.description}</small>}<small>{words.open} →</small></div>
   </Link>)}</div>:<p>{words.empty}</p>}
 </section>
}
