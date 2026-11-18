import {useEffect,useState} from 'react'
import {api} from '../api'

const WORDS={
 ar:{title:'خدمات وصلني',empty:'لا توجد خدمات متاحة في منطقتك حالياً',loading:'جارٍ تحميل الخدمات…'},
 en:{title:'Waselni services',empty:'No services are available in your area yet',loading:'Loading services…'},
 he:{title:'שירותי Waselni',empty:'אין שירותים זמינים באזורך כעת',loading:'טוען שירותים…'},
}

/** Customer-facing directory of services the administration has switched on. */
export default function PublicServices({lang='ar'}){
 const words=WORDS[lang]||WORDS.ar
 const [services,setServices]=useState(null),[error,setError]=useState('')
 useEffect(()=>{let live=true;api(`/services/?lang=${lang}`).then(rows=>{if(live)setServices(Array.isArray(rows)?rows:[])}).catch(err=>{if(live)setError(err.message)});return()=>{live=false}},[lang])
 if(error||!services||!services.length)return null
 return <section className="panel public-services" aria-label={words.title}>
  <div className="section-head"><div><h3>{words.title}</h3></div><span className="count-pill">{services.length}</span></div>
  <div className="public-services-grid">{services.map(service=><article key={service.code} className="public-service"><span className="feature-icon">{service.icon?<span aria-hidden="true">{service.icon}</span>:'✦'}</span><div><b>{service.name}</b>{service.description&&<small>{service.description}</small>}</div></article>)}</div>
 </section>
}
