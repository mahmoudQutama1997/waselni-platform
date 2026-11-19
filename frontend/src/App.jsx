import CustomerStorefront from './customer/CustomerStorefront.tsx'
import L from './map/leaflet'
import React,{useEffect,useMemo,useState,useRef} from 'react'
import {Routes,Route,Link,NavLink,Navigate,useLocation,useNavigate} from 'react-router-dom'
import {api,login,token,orderSocket,clearAuth,mediaUrl,roundCoordinate} from './api'
import {createTileLayer} from './map/tiles'
import {mapMarker,createMarkerIcon} from './map/markers'
import DeliveryMap from './map/DeliveryMap'
import {isValidLatLng,isLocationStale} from './map/routing'
import {makeMapLabels} from './map/labels'
import SafeImage from './components/SafeImage'
import ErrorBoundary from './components/ErrorBoundary'
import AdminControlCenter from './portals/AdminControlCenter.jsx'
import PublicServices from './portals/PublicServices.jsx'
import {CaptainServicesPanel,CaptainSchedulePanel,CaptainEarningsPanel} from './portals/CaptainServices.jsx'
import MerchantOperations from './portals/MerchantOperations.jsx'
import AdminCaptainServices from './portals/AdminCaptainServices.jsx'
import ProofDialog from './portals/ProofDialog.jsx'
import {setStadiaRole,clearStadiaKey} from './map/stadiaAuth'

import {makeCoalescedLoader,uniqueRows} from './lib/polling.js'
const newRequestKey=()=>globalThis.crypto?.randomUUID?.()||`waselni-${Date.now()}-${Math.random().toString(36).slice(2)}`;
import {dict} from './i18n'
import NavIcon from './pwa/navIcons.jsx'
import ServiceIcon from './components/ServiceIcon'
import MobileNav from './pwa/MobileNav.jsx'
import PwaBanners from './pwa/PwaBanners.jsx'
import ConfirmHost,{confirmAction} from './pwa/confirm.jsx'
import {unlockAlertAudio,playOrderAlert,showOrderNotification} from './pwa/alerts.js'
import NotificationToggle from './pwa/NotificationToggle.jsx'
import NotificationCenter from './pwa/NotificationCenter.jsx'
import {exportCsv} from './exportCsv.js'
import {MAP_TILE_URL,MAP_ATTRIBUTION,GEOCODING_REVERSE_URL,GEOCODING_SEARCH_URL,geocodeUrl} from './config'
const money=v=>`${Number(v||0).toFixed(2)} ₪`
const OSRM_BASE=(import.meta.env.VITE_OSRM_URL||'https://router.project-osrm.org').replace(/\/+$/,'')
const GEOCODING_BASE=GEOCODING_REVERSE_URL
const statusLabel=(t,s)=>t[s]||s
const stockTone=p=>p.stock_status==='out'?'is-out':p.stock_status==='low'?'is-low':p.stock_status==='in'?'is-in':'is-untracked'
const stockText=(t,p)=>p.stock_status==='out'?t.outOfStock:p.stock_status==='low'?t.lowStock:p.stock_status==='in'?t.inStock:t.untrackedStock
const fillText=(text,values)=>String(text||'').replace(/\{(\w+)\}/g,(match,key)=>values[key]??match)
const APP_ROLE=(import.meta.env.VITE_WASELNI_APP_ROLE||'all').toLowerCase()
const APP_ROLE_LABEL={customer:'تطبيق الزبون',captain:'تطبيق الكابتن',merchant:'تطبيق التاجر',admin:'لوحة الإدارة',all:'وصلني'}
const PAGE_TITLE_KEY={orders:'orders',ride:'rideService',catalog:'catalog',reports:'reports',account:'accountProfile',profile:'profile',captain:'captain',settlements:'settlements',admin:'dashboard',support:'support',operations:'storeManagement'}
function useOnline(){
 const [online,setOnline]=useState(()=>typeof navigator==='undefined'?true:navigator.onLine);
 useEffect(()=>{const up=()=>setOnline(true),down=()=>setOnline(false);window.addEventListener('online',up);window.addEventListener('offline',down);return()=>{window.removeEventListener('online',up);window.removeEventListener('offline',down)}},[]);
 return online;
}

// A single app-level toast layer keeps feedback above sticky navigation, cards and maps.
function notify(message, type='success') {
 if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('waselni:toast',{detail:{message:String(message||''),type}}));
}
function ToastViewport({t}){
 const [items,setItems]=useState([]);
 useEffect(()=>{
  const onToast=e=>{
   const id=`${Date.now()}-${Math.random()}`;
   const item={id,message:e.detail?.message||'',type:e.detail?.type||'success'};
   setItems(old=>[...old.slice(-2),item]);
   window.setTimeout(()=>setItems(old=>old.filter(x=>x.id!==id)),5000);
  };
  window.addEventListener('waselni:toast',onToast);
  return()=>window.removeEventListener('waselni:toast',onToast);
 },[]);
 return <div className="toast-viewport" aria-live="polite" aria-atomic="false">{items.map(item=><div key={item.id} className={`app-toast ${item.type==='error'?'toast-error':'toast-success'}`} role={item.type==='error'?'alert':'status'}><span className="toast-indicator">{item.type==='error'?'!':'✓'}</span><span className="toast-message">{item.message}</span><button type="button" className="toast-close" aria-label={t.dismissNotification} onClick={()=>setItems(old=>old.filter(x=>x.id!==item.id))}>×</button></div>)}</div>;
}
const ALERT_LABELS={ar:{newOrder:'طلب جديد',order:'طلب'},he:{newOrder:'הזמנה חדשה',order:'הזמנה'},en:{newOrder:'New order',order:'Order'}}
function useOrderAlerts(role,t,lang){
 useEffect(()=>{
  if(!role)return undefined
  const labels=ALERT_LABELS[lang]||ALERT_LABELS.ar
  unlockAlertAudio()
  const unlock=()=>unlockAlertAudio()
  window.addEventListener('pointerdown',unlock,{once:true})
  window.addEventListener('keydown',unlock,{once:true})
  const seen=new Map()
  const subscription=orderSocket((message)=>{
   if(!message||typeof message.type!=='string')return
   if(!message.type.startsWith('order.'))return
   const key=`${message.type}:${message.order_id}:${message.status}`
   const now=Date.now()
   if(seen.get(key)&&now-seen.get(key)<12000)return
   if(seen.size>200)seen.clear()
   seen.set(key,now)
   const newForMerchant=role==='merchant'&&message.type==='order.created'
   const newForCaptain=role==='captain'&&(message.type==='order.created'||message.type==='order.ready')
   if(newForMerchant||newForCaptain){
    playOrderAlert()
    const orderReference=message.order_number?` #${message.order_number}`:''
    notify(`${labels.newOrder}${orderReference}`,'success')
    showOrderNotification(labels.newOrder,`${labels.order}${orderReference} · ${statusLabel(t,message.status)}`,`order-${message.order_id}`)
   }else if(role==='customer'){
    const orderReference=message.order_number?` #${message.order_number}`:''
    notify(`${statusLabel(t,message.status)} · ${labels.order}${orderReference}`,'success')
   }else if(role==='admin'&&message.type==='order.created'){
    const orderReference=message.order_number?` #${message.order_number}`:''
    notify(`${labels.newOrder}${orderReference}`,'success')
   }
  })
  return ()=>{subscription?.close();window.removeEventListener('pointerdown',unlock);window.removeEventListener('keydown',unlock)}
 },[role,t,lang])
}
function App(){
 const [lang,setLang]=useState(localStorage.getItem('waselni_lang')||'ar')
 const [me,setMe]=useState(null),[error,setError]=useState(''),[passwordError,setPasswordError]=useState(''),[registering,setRegistering]=useState(false),[registerError,setRegisterError]=useState(''),[registerNotice,setRegisterNotice]=useState('')
 const t=dict[lang],rtl=lang!=='en'
 const passwordResetLink=useMemo(()=>{const prefix='#password-reset?';if(!window.location.hash.startsWith(prefix))return null;const params=new URLSearchParams(window.location.hash.slice(prefix.length));return {uid:params.get('uid'),token:params.get('token')}},[])
 const [recoveryMode,setRecoveryMode]=useState(()=>passwordResetLink?.uid&&passwordResetLink?.token?'confirm':null),[recoveryError,setRecoveryError]=useState(''),[recoveryNotice,setRecoveryNotice]=useState('')
 const appRoleLabel=t[({customer:'appRoleCustomer',captain:'appRoleCaptain',merchant:'appRoleMerchant',admin:'appRoleAdmin',all:'appRoleAll'})[APP_ROLE]]||APP_ROLE_LABEL[APP_ROLE]||APP_ROLE
 useOrderAlerts(me?.role,t,lang)
 useEffect(()=>{document.documentElement.lang=lang;document.documentElement.dir=rtl?'rtl':'ltr';localStorage.setItem('waselni_lang',lang)},[lang])
 useEffect(()=>{if(passwordResetLink?.uid&&passwordResetLink?.token){clearStadiaKey();clearAuth();window.history.replaceState(null,'',window.location.pathname+window.location.search);return}if(token())api('/me/').then(user=>{if(APP_ROLE!=='all'&&user.role!==APP_ROLE){clearStadiaKey();clearAuth();setError(`هذا الحساب لا يملك صلاحية الدخول إلى ${APP_ROLE_LABEL[APP_ROLE]||APP_ROLE}.`);return}setMe(user)}).catch(()=>{clearStadiaKey();clearAuth()})},[])
 useEffect(()=>{setStadiaRole(me?.role||null)},[me])
 const location=useLocation()
 const online=useOnline()
 async function signIn(e){e.preventDefault();setError('');const fd=new FormData(e.currentTarget);try{await login(fd.get('username'),fd.get('password'));const user=await api('/me/');if(APP_ROLE!=='all'&&user.role!==APP_ROLE){clearStadiaKey();clearAuth();throw new Error(`${t.roleMismatch||'هذا الحساب لا يملك صلاحية الدخول إلى'} ${appRoleLabel}.`)}setMe(user)}catch(x){setError(x.message)}}
 async function signUp(e){e.preventDefault();setRegisterError('');setRegisterNotice('');const fd=new FormData(e.currentTarget);fd.set('role','customer');try{const result=await api('/auth/register/',{method:'POST',body:fd});setRegisterNotice(`${result.message} Username: ${result.username}`);setRegistering(false)}catch(x){setRegisterError(x.message)}}
 async function requestPasswordReset(e){e.preventDefault();setRecoveryError('');setRecoveryNotice('');const fd=new FormData(e.currentTarget);try{const result=await api('/auth/password-reset/',{method:'POST',body:JSON.stringify({email:fd.get('email')})});setRecoveryNotice(result.detail)}catch(x){setRecoveryError(x.message)}}
 async function confirmPasswordReset(e){e.preventDefault();setRecoveryError('');setRecoveryNotice('');if(!passwordResetLink?.uid||!passwordResetLink?.token){setRecoveryError(t.passwordResetInvalid);return}const fd=new FormData(e.currentTarget);try{await api('/auth/password-reset/confirm/',{method:'POST',body:JSON.stringify({uid:passwordResetLink.uid,token:passwordResetLink.token,new_password:fd.get('new_password'),confirm_password:fd.get('confirm_password')})});clearAuth();window.history.replaceState(null,'',window.location.pathname+window.location.search);setRecoveryMode(null);setRecoveryNotice(t.passwordResetComplete)}catch(x){setRecoveryError(x.message)}}
 function signOut(){clearStadiaKey();clearAuth();setMe(null)}
 async function changeInitialPassword(e){e.preventDefault();setPasswordError('');const fd=new FormData(e.currentTarget);try{await api('/account/change-password/',{method:'POST',body:JSON.stringify({current_password:fd.get('current_password'),new_password:fd.get('new_password')})});setMe(await api('/me/'))}catch(x){setPasswordError(x.message)}}
 if(!me)return <>
  <PwaBanners lang={lang} showInstallPrompt={false}/>
  <main className="login-shell">
   <section className="login-card auth-card">
    <div className="brand-mark">و</div>
    <h1>{t.brand}</h1>
    <p>{APP_ROLE==='all'?t.tagline:appRoleLabel}</p>
    <label>{t.language}</label>
    <select value={lang} onChange={e=>setLang(e.target.value)}>
     <option value="ar">العربية</option><option value="he">עברית</option><option value="en">English</option>
    </select>
    {recoveryMode==='request'?<>
     <h3>{t.passwordResetTitle}</h3><p>{t.passwordResetHint}</p>
     <form onSubmit={requestPasswordReset}><label>{t.email}</label><input name="email" type="email" required autoComplete="email"/><button>{t.passwordResetSend}</button>{recoveryError&&<p className="error">{recoveryError}</p>}{recoveryNotice&&<p className="success-note">{recoveryNotice}</p>}</form>
     <button type="button" className="secondary auth-switch" onClick={()=>{setRecoveryMode(null);setRecoveryError('');setRecoveryNotice('')}}>{t.backToLogin}</button>
    </>:recoveryMode==='confirm'?<>
     <h3>{t.passwordResetNewTitle}</h3><p>{t.passwordResetNewHint}</p>
     <form onSubmit={confirmPasswordReset}><label>{t.newPassword}</label><input name="new_password" type="password" minLength="8" required autoComplete="new-password"/><label>{t.confirmPassword}</label><input name="confirm_password" type="password" minLength="8" required autoComplete="new-password"/><button>{t.passwordResetSave}</button>{recoveryError&&<p className="error">{recoveryError}</p>}</form>
    </>:!registering?<>
     <form onSubmit={signIn}>
      <label>{t.username}</label><input name="username" required/>
      <label>{t.password}</label><input name="password" type="password" required/>
      <button>{t.enter}</button>{error&&<p className="error">{error}</p>}
     </form>
     <button type="button" className="secondary auth-switch" onClick={()=>{setRecoveryMode('request');setRecoveryError('');setRecoveryNotice('');setError('')}}>{t.forgotPassword}</button>
     {(APP_ROLE==='customer'||APP_ROLE==='all')&&<button type="button" className="secondary auth-switch" onClick={()=>{setRegistering(true);setError('');setRegisterNotice('')}}>{t.createCustomerAccount}</button>}
    </>:<>
     <h3>{t.registerTitle}</h3>
     <form onSubmit={signUp} className="form-stack registration-form" encType="multipart/form-data">
      <input type="hidden" name="role" value="customer"/><p className="note">{t.registerNote}</p>
      <label>{t.username}<input name="username" required minLength="3" autoComplete="username"/></label>
      <label>{t.firstName}<input name="first_name" required/></label>
      <label>{t.lastName}<input name="last_name"/></label>
      <label>{t.phone}<input name="phone" required/></label>
      <label>{t.email}<input name="email" type="email"/></label>
      <label>{t.password}<input name="password" type="password" minLength="8" required autoComplete="new-password"/></label>
      <label>{t.profileImage}<input name="profile_image" type="file" accept="image/png,image/jpeg,image/webp"/></label>
      <div data-role-field="merchant" hidden>
       <label>اسم المتجر<input name="shop_name"/></label><label>تصنيف المتجر<input name="category" placeholder="general"/></label>
       <label>وصف المتجر<textarea name="description"/></label><label>عنوان المتجر<input name="address"/></label>
       <label>شعار المتجر<input name="store_image" type="file" accept="image/png,image/jpeg,image/webp"/></label>
       <label>صورة الغلاف<input name="cover_image" type="file" accept="image/png,image/jpeg,image/webp"/></label>
      </div>
      <div data-role-field="captain" hidden>
       <label>نوع المركبة<select name="vehicle_type"><option value="motorcycle">دراجة نارية</option><option value="car">سيارة</option><option value="truck">شاحنة</option></select></label>
       <label>موديل المركبة<input name="vehicle_model"/></label><label>رقم اللوحة<input name="plate_number"/></label>
       <label>نوع التصريح<select name="permit_type"><option value="west_bank">الضفة الغربية</option><option value="jerusalem_id">هوية القدس</option><option value="work_permit">تصريح عمل</option></select></label>
       <label>وثيقة الهوية / التصريح<input name="identity_document" type="file" accept=".pdf,.jpg,.jpeg,.png"/></label>
       <label>رخصة القيادة<input name="driving_license_document" type="file" accept=".pdf,.jpg,.jpeg,.png"/></label>
       <label>التأمين<input name="insurance_document" type="file" accept=".pdf,.jpg,.jpeg,.png"/></label>
       <label className="check-label"><input name="digital_undertaking" type="checkbox" value="true" required disabled/>أتعهد بصحة البيانات والالتزام بشروط العمل والسلامة في وصلني</label>
      </div>
      <button>{t.completeRegistration}</button>{registerError&&<p className="error">{registerError}</p>}
     </form>
     {(APP_ROLE==='customer'||APP_ROLE==='all')&&<button type="button" className="secondary auth-switch" onClick={()=>setRegistering(false)}>{t.backToLogin}</button>}
    </>}
    {registerNotice&&<p className="success-note">{registerNotice}</p>}{recoveryNotice&&recoveryMode===null&&<p className="success-note">{recoveryNotice}</p>}<small>{t.rolesFooter}</small>
   </section>
  </main>
 </>
 if(me.must_change_password)return <main className="login-shell"><section className="login-card"><div className="brand-mark">و</div><h1>{t.changePasswordTitle}</h1><p>{t.changePasswordNote}</p><form onSubmit={changeInitialPassword}><label>{t.currentPassword}</label><input name="current_password" type="password" required/><label>{t.newPassword}</label><input name="new_password" type="password" minLength={8} required/><button>{t.changePassword}</button>{passwordError&&<p className="error">{passwordError}</p>}</form><button className="ghost" onClick={signOut}>{t.logout}</button></section></main>
 const role=me.role
 const pageKey=location.pathname==='/'?'home':location.pathname.slice(1).split('/')[0]
 const titleKey=pageKey==='home'?'home':(PAGE_TITLE_KEY[pageKey]||'home')
 const subtitle=pageKey==='home'?(role==='admin'?t.overview:role==='captain'?t.captainWorkspace:role==='merchant'?t.liveUpdates:t.tagline):(pageKey==='orders'?t.liveUpdates:pageKey==='catalog'?t.catalogSubtitle:pageKey==='admin'?t.overview:pageKey==='settlements'?t.settlementWorkflowHint:pageKey==='ride'?t.rideSubtitle:pageKey==='support'?t.ticketDetails||t.support:'')
 return <div className="app" data-role={role}><PwaBanners lang={lang}/><ConfirmHost lang={lang}/><ToastViewport t={t}/><aside className="sidebar"><div className="side-brand"><span className="brand-mark small">و</span><b>{t.brand}</b></div><Link className="user-chip" to="/account" title={t.accountProfile}><span className="user-chip-avatar">{me.profile_image?<SafeImage src={me.profile_image} alt=""/>:<span>◉</span>}</span><span><strong>{me.first_name||me.username}</strong><small>{t[`${role}Role`]||t[role]||role}</small></span></Link><nav aria-label={t.platform}>
 <NavLink to="/" end><NavIcon name="home"/>{t.home}</NavLink><NavLink to="/account"><NavIcon name="user"/>{t.accountProfile}</NavLink><NavLink to="/orders"><NavIcon name="orders"/>{t.orders}</NavLink>{role==='customer'&&<NavLink to="/ride"><NavIcon name="ride"/>{t.rideService}</NavLink>}{role==='merchant'&&<><NavLink to="/operations"><NavIcon name="store"/>{t.storeManagement||t.profile}</NavLink><NavLink to="/catalog"><NavIcon name="catalog"/>{t.catalog}</NavLink><NavLink to="/reports"><NavIcon name="reports"/>{t.reports}</NavLink><NavLink to="/profile"><NavIcon name="store"/>{t.profile}</NavLink><NavLink to="/settlements"><NavIcon name="money"/>{t.settlements}</NavLink></>}{role==='captain'&&<><NavLink to="/captain"><NavIcon name="captain"/>{t.captain}</NavLink><NavLink to="/settlements"><NavIcon name="money"/>{t.settlements}</NavLink></>}{role==='admin'&&<><NavLink to="/admin"><NavIcon name="dashboard"/>{t.controlCenter||t.dashboard}</NavLink><NavLink to="/settlements"><NavIcon name="money"/>{t.settlements}</NavLink><NavLink to="/support"><NavIcon name="support"/>{t.support}</NavLink></>}
 {me.is_finance_staff&&role!=='admin'&&<NavLink to="/settlements"><NavIcon name="money"/>{t.settlements}</NavLink>}
 {role!=='admin'&&<NavLink to="/support"><NavIcon name="support"/>{t.support}</NavLink>}
 </nav><div className="side-bottom"><select value={lang} onChange={e=>setLang(e.target.value)} aria-label={t.language}><option value="ar">العربية</option><option value="he">עברית</option><option value="en">English</option></select><button className="ghost" onClick={signOut}>{t.logout}</button></div></aside>
 <main className="content"><header><div className="header-title"><span className="eyebrow">{t.platform.toUpperCase()} · {t[role]||role}</span><h2>{t[titleKey]||t.home}</h2>{subtitle&&<p className="header-subtitle">{subtitle}</p>}</div><div className="header-actions"><NotificationCenter lang={lang} role={role}/><span className={`status-pill ${online?'':'is-offline'}`} title={online?t.online:t.offline}>{online?t.online:t.offline}</span></div></header>
 <ErrorBoundary lang={lang} resetKey={location.pathname}><Routes><Route path="/" element={<Home role={role} t={t} lang={lang}/>}/><Route path="/orders" element={<Orders role={role} t={t}/>}/><Route path="/ride" element={role==='customer'?<RideBooking t={t} lang={lang} role={role}/>:<Navigate to="/"/>}/><Route path="/catalog" element={role==='merchant'?<Catalog t={t}/>:<Navigate to="/"/>}/><Route path="/operations" element={role==='merchant'?<MerchantOperations t={t} lang={lang}/>:<Navigate to="/"/>}/><Route path="/reports" element={<Reports t={t}/>}/><Route path="/account" element={<AccountProfile t={t} me={me} setMe={setMe} onSignOut={signOut} lang={lang}/>}/><Route path="/profile" element={role==='merchant'?<Profile t={t} lang={lang}/>:<Navigate to="/account"/>}/><Route path="/captain" element={<Captain t={t} lang={lang}/>}/><Route path="/settlements" element={<Settlements t={t} role={role} canManageFinance={role==='admin'||!!me.is_finance_staff}/>}/><Route path="/admin" element={role==='admin'?<AdminControlCenter lang={lang}/>:<Navigate to="/"/>}/><Route path="/admin/:section" element={role==='admin'?<AdminControlCenter lang={lang}/>:<Navigate to="/"/>}/><Route path="/admin/legacy" element={role==='admin'?<Admin t={t}/>:<Navigate to="/"/>}/><Route path="/support" element={<Support t={t}/>}/><Route path="*" element={<Navigate to="/"/>}/></Routes></ErrorBoundary>
 </main><MobileNav role={role} t={t} isFinanceStaff={!!me.is_finance_staff}/></div>
}

function useLoad(path,onEvent){
 const [data,setData]=useState([]),[err,setErr]=useState('');
 const [updatedAt,setUpdatedAt]=useState(0);
 const [tick,setTick]=useState(0);
 const seq=useRef(0),revision=useRef(0),handler=useRef(onEvent);
 handler.current=onEvent;
 useEffect(()=>{let live=true;
  const load=()=>{
   const mine=++seq.current,rev=revision.current;
   return api(path).then(d=>{
    // A response that started before a newer value arrived must never win.
    if(!live||mine!==seq.current||rev!==revision.current)return;
    setData(uniqueRows(Array.isArray(d)?d:d.results||[]));setErr('');setUpdatedAt(Date.now());
   }).catch(e=>{if(live&&mine===seq.current)setErr(e.message||'')});
  };
  const patch=fn=>{revision.current+=1;setData(fn)};
  // One coalesced refresh serves interval, socket, focus, reconnect and visibility triggers.
  const refresh=makeCoalescedLoader(load,{minGap:1500});
  refresh();
  const timer=setInterval(refresh,5000);
  const ws=orderSocket(m=>{
   if(handler.current)handler.current(m,patch);
   refresh();
  });
  const onVisible=()=>{if(document.visibilityState==='visible')refresh()};
  const onRealtime=e=>{if(e.detail&&e.detail.connected)refresh()};
  window.addEventListener('focus',refresh);
  window.addEventListener('online',refresh);
  window.addEventListener('waselni:realtime',onRealtime);
  document.addEventListener('visibilitychange',onVisible);
  return ()=>{live=false;clearInterval(timer);ws.close();window.removeEventListener('focus',refresh);window.removeEventListener('online',refresh);window.removeEventListener('waselni:realtime',onRealtime);document.removeEventListener('visibilitychange',onVisible)};
 },[path,tick]);
 return {data,err,updatedAt,reload:()=>setTick(t=>t+1)};
}
function Home({role,t,lang}){if(role==='admin')return <AdminControlCenter lang={lang}/>;if(role==='captain')return <Captain t={t}/>;if(role==='merchant')return <MerchantHome t={t} lang={lang}/>;return <><PublicServices lang={lang}/><CustomerStorefront lang={lang}/></>}

function MerchantHome({t,lang}){
 const [tracking,setTracking]=useState([]);
 const [trackError,setTrackError]=useState('');
 useEffect(()=>{
  let live=true,timer=null;
  const schedule=(list)=>{if(timer){clearInterval(timer);timer=null}if(list.length)timer=setInterval(refresh,8000)};
  const load=()=>api('/orders/tracking/').then(d=>{
   if(!live)return;
   const list=uniqueRows(Array.isArray(d)?d:(d?.results||[]));
   setTracking(list);setTrackError('');schedule(list);
  }).catch(e=>{if(live)setTrackError(e.message||t.actionFailed)});
  const refresh=makeCoalescedLoader(load,{minGap:2500});
  refresh();
  const ws=orderSocket(m=>{if(m&&typeof m.type==='string'&&(m.type.startsWith('order.')||m.type.startsWith('captain.')))refresh()});
  const onRealtime=e=>{if(e.detail?.connected)refresh()};
  window.addEventListener('waselni:realtime',onRealtime);
  return ()=>{live=false;if(timer)clearInterval(timer);ws?.close();window.removeEventListener('waselni:realtime',onRealtime)};
 },[t]);
 return <><MerchantTracking orders={tracking} error={trackError} t={t} lang={lang}/><Orders role="merchant" t={t}/><ReceivedRatings t={t}/></>;
}

function MerchantTracking({orders=[],error='',t,lang}){
 const [selectedId,setSelectedId]=useState(null);
 useEffect(()=>{
  if(!orders.length){if(selectedId!==null)setSelectedId(null);return}
  if(!orders.some(o=>o.id===selectedId))setSelectedId(orders[0].id);
 },[orders,selectedId]);
 const order=orders.find(o=>o.id===selectedId)||orders[0]||null;
 const updated=order?.captain_location_updated_at;
 const fresh=updated&&Date.now()-new Date(updated).getTime()<45000;
 const hasCaptainLocation=order?.captain_latitude!=null&&order?.captain_longitude!=null;
 return <section className="panel merchant-tracking">
  <div className="section-head"><div><h3>{t.trackingTitle}</h3><p>{t.trackingHint}</p></div><span className="tracking-live-pill"><i className={order?'is-live':''}/>{t.trackingLive}</span></div>
  {error&&<p className="error">{error}</p>}
  {!orders.length?<div className="tracking-empty"><span>🛰</span><p>{t.trackingEmpty}</p></div>:<>
   {orders.length>1&&<label className="tracking-select">{t.trackingPick}<select value={order?.id||''} onChange={e=>setSelectedId(Number(e.target.value))}>{orders.map(o=><option key={o.id} value={o.id}>{`${o.order_number} · ${o.customer_name||''} · ${statusLabel(t,o.status)}`}</option>)}</select></label>}
   {order&&<>
    <div className="tracking-meta">
     <div className="tracking-captain"><span className="mini-avatar">{order.captain_profile_image?<SafeImage src={order.captain_profile_image} alt={order.captain_name||''}/>:<span>◉</span>}</span><div><small>{t.trackingCaptain}</small><b>{order.captain_name||'—'}</b></div><span className={`tag ${order.status}`}>{statusLabel(t,order.status)}</span></div>
     <div className="tracking-updated"><small>{t.trackingUpdated}</small><b dir="ltr">{updated?new Date(updated).toLocaleString():t.noCaptainLocation}</b>{updated&&<span className={`tracking-indicator ${fresh?'':'is-muted'}`}>{fresh?t.live:t.trackingUnavailable}</span>}</div>
    </div>
    <RideRouteMap order={order} t={t} role="merchant"/>
    {!hasCaptainLocation&&<p className="tracking-unavailable">{t.trackingUnavailable}{updated?` · ${t.trackingUpdated}: ${new Date(updated).toLocaleString()}`:''}</p>}
    <p className="tracking-privacy">🔒 {t.trackingPrivacy}</p>
   </>}
  </>}
 </section>;
}

function RideRouteMap({order,t,role='customer'}){
 const lang=document.documentElement.lang||'ar';
 const labels=makeMapLabels(t,lang,role==='captain'?'captain':role==='merchant'?'merchant':'customer');
 const stage=order.status||'new';
 const statusText=statusLabel(t,stage);
 const pickupOk=isValidLatLng(order.pickup_latitude,order.pickup_longitude);
 const dropOk=isValidLatLng(order.dropoff_latitude,order.dropoff_longitude);
 const captainOk=order.captain_latitude!=null&&order.captain_longitude!=null&&isValidLatLng(order.captain_latitude,order.captain_longitude);
 // The API withholds captain coordinates unless a captain is assigned, so the
 // marker appears only once the order really has one.
 const captainVisible=Boolean(order.captain)&&captainOk;
 const stale=captainVisible&&isLocationStale(order.captain_location_updated_at);
 const carrying=['picked_up','delivering','awaiting_confirmation','completed'].includes(stage);
 const points=[];
 if(pickupOk)points.push({id:'store-'+order.id,kind:'store',lat:order.pickup_latitude,lng:order.pickup_longitude,label:order.merchant_name||labels.store,sublabel:order.pickup_address||'',popup:{title:order.merchant_name||labels.store,lines:[order.pickup_address,t.status+': '+statusText]}});
 if(dropOk)points.push({id:'customer-'+order.id,kind:'customer',lat:order.dropoff_latitude,lng:order.dropoff_longitude,label:labels.customer,sublabel:order.dropoff_address||'',popup:{title:labels.customer,lines:[order.dropoff_address,order.customer_name?t.customerName+': '+order.customer_name:null,order.dropoff_notes]}});
 if(captainVisible)points.push({id:'captain-'+order.id,kind:'captain',lat:Number(order.captain_latitude),lng:Number(order.captain_longitude),label:order.captain_name||labels.captain,assigned:true,stale,sublabel:stale?labels.stale:labels.live,popup:{title:order.captain_name||labels.captain,image:order.captain_profile_image,lines:[order.captain_location_updated_at?labels.updated+': '+new Date(order.captain_location_updated_at).toLocaleString():null,stale?labels.stale:labels.live,carrying?labels.destination:labels.pickup]}});
 // Route follows the real delivery stage: captain to store before pickup, then
 // captain to the customer; otherwise the store-to-customer leg.
 let route=null;
 const captainPoint=[Number(order.captain_latitude),Number(order.captain_longitude)];
 if(captainVisible&&stage==='assigned'&&role==='captain'&&pickupOk){
  route={from:captainPoint,to:[Number(order.pickup_latitude),Number(order.pickup_longitude)]};
 }else if(captainVisible&&carrying&&dropOk&&stage!=='completed'){
  route={from:captainPoint,to:[Number(order.dropoff_latitude),Number(order.dropoff_longitude)]};
 }else if(pickupOk&&dropOk){
  route={from:[Number(order.pickup_latitude),Number(order.pickup_longitude)],to:[Number(order.dropoff_latitude),Number(order.dropoff_longitude)]};
 }
 if(!pickupOk&&!dropOk)return <div className="ride-map-missing">{labels.noPoints}</div>;
 const legend=[{kind:'store',label:order.merchant_name||labels.store},{kind:'customer',label:labels.customer}];
 if(captainVisible)legend.push({kind:'captain',label:order.captain_name||labels.captain});
 const live=stage!=='completed'&&stage!=='cancelled';
 return <div className="captain-ride-map-wrap">
  <div className="captain-map-heading"><b>{live?(t.liveTrackingTitle||t.routeMapTitle):(t.completed||statusText)}</b><div className="map-heading-tags"><span className={'tag '+stage}>{statusText}</span><span className={captainVisible&&!stale&&live?'tracking-indicator':'tracking-indicator is-muted'}>{captainVisible?(live?(stale?labels.stale:labels.live):labels.stale):(t.captainLocationUnavailable||'بانتظار موقع الكابتن')}</span></div></div>
  <DeliveryMap points={points} route={route} labels={labels} legend={legend} height={320} fitKey={order.id+'-'+stage}/>
 </div>
}

function OrderProgress({order,t}){
 const steps=order.order_type==='ride'?['new','assigned','picked_up','delivering','awaiting_confirmation','completed']:['new','accepted','preparing','ready','assigned','picked_up','delivering','awaiting_confirmation','completed'];
 const current=steps.indexOf(order.status);
 if(order.status==='cancelled')return <div className="order-progress-cancelled">{t.cancelled}</div>;
 return <div className="order-progress" aria-label={`${t.status}: ${t[order.status]||order.status}`}>
  {steps.map((step,index)=><div key={step} className={`order-progress-step ${index<current?'is-done':''} ${index===current?'is-current':''}`}>
   <span className="progress-node">{index<current?'✓':index+1}</span><small>{t[step]||step}</small>
  </div>)}
 </div>;
}

function OrderActivityList({order,t}){
 const activities=order.activities||[];
 return <details className="order-activity">
  <summary>{t.orderHistory}</summary>
  {activities.length?<ol>{activities.map(activity=><li key={activity.id}>
   <b>{t[`activity_${activity.event}`]||t.activity_status_changed}</b>
   <span>{activity.actor_name}</span>
   {activity.from_status&&activity.from_status!==activity.to_status&&<small>{statusLabel(t,activity.from_status)} → {statusLabel(t,activity.to_status)}</small>}
   <time dateTime={activity.created_at}>{new Date(activity.created_at).toLocaleString()}</time>
  </li>)}</ol>:<p className="muted-note">{t.orderHistoryNotAvailable}</p>}
 </details>;
}

function ReceiptConfirmation({order,t,busy,onConfirm}){
 if(order.status!=='awaiting_confirmation')return null;
 return <button disabled={busy} onClick={()=>onConfirm(order)}>
  {busy?t.actionInProgress:t.confirmReceipt}
 </button>;
}

function RatingForm({order,targetType,label,t,onSaved}){
 const existing=(order.my_ratings||[]).find(rating=>rating.target_type===targetType);
 const [score,setScore]=useState(String(existing?.score||5));
 const [comment,setComment]=useState(existing?.comment||'');
 const [busy,setBusy]=useState(false);
 useEffect(()=>{setScore(String(existing?.score||5));setComment(existing?.comment||'')},[existing?.score,existing?.comment]);
 async function submit(event){
  event.preventDefault();
  setBusy(true);
  try{
   await api('/ratings/',{method:'POST',body:JSON.stringify({order:order.id,target_type:targetType,score:Number(score),comment})});
   notify(t.ratingSaved,'success');
   onSaved();
  }catch(error){notify(error.message||t.actionFailed,'error')}
  finally{setBusy(false)}
 }
 return <form className="order-rating" onSubmit={submit}>
  <b>{label}</b>
  <label>{t.ratingScore}<select value={score} onChange={event=>setScore(event.target.value)}>{[5,4,3,2,1].map(value=><option key={value} value={value}>{value} / 5</option>)}</select></label>
  <label>{t.ratingComment}<textarea value={comment} maxLength={1000} onChange={event=>setComment(event.target.value)}/></label>
  <button disabled={busy}>{busy?t.actionInProgress:(existing?t.updateRating:t.submitRating)}</button>
 </form>;
}

function OrderRating({order,t,onSaved}){
 if(order.status!=='completed')return null;
 return <div className="order-ratings">
  {order.captain_rating!=null&&<small>{t.averageRating}: {order.captain_rating} / 5</small>}
  {order.merchant_rating!=null&&<small>{t.averageRating}: {order.merchant_rating} / 5</small>}
  {order.captain&&<RatingForm order={order} targetType="captain" label={t.rateCaptain} t={t} onSaved={onSaved}/>}
  {order.order_type==='store'&&order.merchant&&<RatingForm order={order} targetType="merchant" label={t.rateMerchant} t={t} onSaved={onSaved}/>}
 </div>;
}

function ReceivedRatings({t}){
 const {data,err}=useLoad('/ratings/');
 return <section className="panel received-ratings">
  <div className="section-head"><div><h3>{t.customerFeedback}</h3><p>{t.averageRating}</p></div></div>
  {err&&<p className="error">{err}</p>}
  {data.length?<div className="order-grid">{data.slice(0,20).map(rating=><article className="order-card" key={rating.id}>
   <div className="card-top"><b>{t.orderPrefix} {rating.order_number}</b><span className="tag">{rating.score} / 5</span></div>
   <p>{t[`${rating.target_type}Role`]||t[rating.target_type]||rating.target_type}</p>
   {rating.comment&&<p>{rating.comment}</p>}
   <small>{new Date(rating.created_at).toLocaleString()}</small>
  </article>)}</div>:!err&&<EmptyText text={t.noReviews}/>}
 </section>;
}

function Orders({role,t}){
 const path=role==='captain'?'/orders/available/':'/orders/';
 const {data,err,reload}=useLoad(path);
 const [mins,setMins]=useState({});
 const [clock,setClock]=useState(Date.now());
 const [query,setQuery]=useState('');
 const [statusFilter,setStatusFilter]=useState('all');
 const [busy,setBusy]=useState(null);
 const [proofOrder,setProofOrder]=useState(null);
 useEffect(()=>{const id=setInterval(()=>setClock(Date.now()),1000);return()=>clearInterval(id)},[]);
 const searchTerm=query.trim().toLowerCase();
 const filtered=data.filter(o=>{
  const matchesQuery=!searchTerm||`${o.order_number||''} ${role==='admin'?o.id:''} ${o.merchant_name||''} ${o.customer_name||''} ${o.captain_name||''} ${o.dropoff_address||''}`.toLowerCase().includes(searchTerm);
  const matchesStatus=statusFilter==='all'||(statusFilter==='active'?!['completed','cancelled'].includes(o.status):o.status===statusFilter);
  return matchesQuery&&matchesStatus;
 });
 const activeCount=data.filter(o=>!['completed','cancelled'].includes(o.status)).length;
 const completedCount=data.filter(o=>o.status==='completed').length;
 const earnings=data.filter(o=>o.status==='completed').reduce((sum,o)=>sum+Number(o.delivery_fee||0),0);
 async function act(url,body,orderId){
  if(orderId&&busy===orderId)return false;
  if(orderId)setBusy(orderId);
  try{await api(url,{method:'POST',body:JSON.stringify(body)});reload();notify(t.actionCompleted,'success');return true}
  catch(e){notify(e.message||t.actionFailed,'error');return false}
  finally{if(orderId)setBusy(null)}
 }
 function exportOrders(){
  exportCsv('waselni-orders.csv',[
   {key:'order_number',label:t.csvOrderId},{key:'status',label:t.csvStatus},
   {key:'customer_name',label:t.csvCustomer},{key:'merchant_name',label:t.csvMerchant},
   {key:'captain_name',label:t.csvCaptain},{key:'total',label:t.csvTotal},
   {key:'delivery_fee',label:t.csvDeliveryFee},{key:'created_at',label:t.csvDate},
  ],filtered);
 }
 return <>
  <div className="section-head"><div><h3>{t.orders}</h3><p>{t.liveUpdates}</p></div><div className="row-actions"><button className="secondary" onClick={exportOrders} disabled={!filtered.length}>{t.exportCsv}</button><button className="secondary" onClick={reload}>{t.refresh}</button></div></div>
  {(role==='captain'||role==='merchant')&&<div className="stats captain-summary"><Stat label={t.active} value={activeCount} icon="active"/><Stat label={t.orders} value={data.length} icon="orders"/><Stat label={role==='captain'?(t.deliveryEarnings||t.sales):t.completedToday} value={role==='captain'?money(earnings):completedCount} icon="sales"/><Stat label={t.completedToday} value={completedCount} icon="completed"/></div>}
  <div className="filter-bar"><div className="search-field"><span aria-hidden="true">⌕</span><input value={query} onChange={e=>setQuery(e.target.value)} placeholder={t.searchOrders||t.search} aria-label={t.searchOrders||t.search}/></div>{[['all',t.allOrders||t.orders],['new',t.new],['active',t.active],['completed',t.completed],['cancelled',t.cancelled]].map(([id,label])=><button key={id} type="button" className={`filter-chip ${statusFilter===id?'is-active':''}`} onClick={()=>setStatusFilter(id)} aria-pressed={statusFilter===id}>{label}</button>)}</div>
  {err&&<p className="error">{err}</p>}
  {!filtered.length&&(searchTerm||statusFilter!=='all'?<EmptyText text={t.noSearchResults}/>:<Empty t={t}/>)}
  <div className="order-grid">{filtered.map(o=><article className="order-card" key={o.id}>
   <div className="card-top"><b>{o.order_number}</b><span className="card-top-tags">{o.service_type&&<span className="service-pill">{t[`service_${o.service_type}`]||o.service_type}</span>}<span className={`tag ${o.status}`}>{statusLabel(t,o.status)}</span></span></div>
   <div className="order-times"><small>{t.createdAt}: {o.created_at?new Date(o.created_at).toLocaleString():'—'}</small><small>{t.updatedAt}: {o.updated_at?new Date(o.updated_at).toLocaleString():'—'}</small></div>
   <h3 className="order-title"><ServiceIcon size="sm" name={o.order_type==='ride'?'vespa':o.order_type==='parcel'?'truck':'store'}/>{o.order_type==='ride'?t.rideService:o.order_type==='parcel'?(t.shipping||t.orders):(o.merchant_name||o.order_type)}</h3>
   <OrderProgress order={o} t={t}/>
   {o.completed_at&&<p className="note">{t.completedAt}: {new Date(o.completed_at).toLocaleString()}</p>}
   <div className="order-person"><span className="mini-avatar">{o.customer_profile_image?<SafeImage src={o.customer_profile_image} alt={o.customer_name||''}/>:<span>◉</span>}</span><p>{t.customerName}: {o.customer_name||'—'}</p></div>
   {o.captain_name&&<div className="order-person"><span className="mini-avatar">{o.captain_profile_image?<SafeImage src={o.captain_profile_image} alt={o.captain_name||''}/>:<span>◉</span>}</span><p>{t.captainName}: {o.captain_name}</p></div>}
   <p>{t.total}: <b>{money(o.total)}</b></p>
   <p>{t.proposedDeliveryFee}: <b>{money(o.delivery_fee)}</b> · {o.captain_accepted_at?t.captainAcceptedPrice:t.waitingCaptainPrice}</p>
   {role==='customer'&&<p className="note">{t.paymentStatus}: {o.payment_method==='cash'?t.cashPayableToCaptain:t.onlinePaymentNotIntegrated}</p>}
   {role==='merchant'&&o.status==='preparing'&&o.accepted_at&&<p className="note">{t.prepTimeLeft||'الوقت المتبقي للتجهيز'}: <b>{Math.max(0,Math.ceil((new Date(o.accepted_at).getTime()+Number(o.prep_minutes||0)*60000-clock)/1000/60))} {t.minutesShort||'دقيقة'}</b></p>}
   {(role==='captain'||role==='merchant')&&o.merchant_arrived_at&&<p className="note">{t.captainArrivedStore||'تم وصول الكابتن للمتجر'}: {new Date(o.merchant_arrived_at).toLocaleTimeString()}</p>}
   <p>{o.pickup_address||'—'} {o.order_type==='ride'?'→':''} {o.dropoff_address||'—'}</p>
   {o.dropoff_notes&&<p className="note">{t.deliveryDetails||'تفاصيل التوصيل'}: {o.dropoff_notes}</p>}
   {o.cancellation_reason&&<p className="note">{t.cancellationReason}: {o.cancellation_reason}</p>}
   {role==='customer'&&o.delivery_otp&&<p className="note">{t.deliveryCode}: <b dir="ltr">{o.delivery_otp}</b> · {t.shareCodeWithCaptain}</p>}
   {['new','ready','assigned','picked_up','delivering'].includes(o.status)&&o.pickup_latitude!=null&&o.dropoff_latitude!=null&&(role==='customer'||role==='captain')&&<RideRouteMap order={o} t={t} role={role}/>}
   <div className="item-list">{(o.items||[]).map((i,n)=><span key={n}>{i.name} × {i.quantity}{i.line_total!=null&&<b> · {money(i.line_total)}</b>}</span>)}</div>
   {role==='merchant'&&o.status==='new'&&<div className="actions"><select value={mins[o.id]||10} onChange={e=>setMins({...mins,[o.id]:Number(e.target.value)})}>{[10,15,20,30,40].map(n=><option key={n}>{n}</option>)}</select><button disabled={busy===o.id} onClick={()=>act(`/orders/${o.id}/accept/`,{prep_minutes:mins[o.id]||10},o.id)}>{busy===o.id?t.actionInProgress:t.accept}</button><button type="button" className="secondary danger" disabled={busy===o.id} onClick={()=>confirmAction({title:t.rejectOrder,message:`${t.orderNumber} ${o.order_number} · ${money(o.total)}`,confirmLabel:t.rejectConfirm,cancelLabel:t.back}).then(ok=>{if(!ok)return;const reason=window.prompt(t.rejectReasonPrompt||'سبب الرفض');if(reason&&reason.trim())act(`/orders/${o.id}/reject/`,{reason:reason.trim()},o.id)})}>{t.rejectOrder}</button></div>}
   {role==='merchant'&&o.status==='accepted'&&<button disabled={busy===o.id} onClick={()=>act(`/orders/${o.id}/status/`,{status:'preparing'},o.id)}>{t.startPreparing}</button>}
   {role==='merchant'&&o.status==='preparing'&&<button disabled={busy===o.id} onClick={()=>act(`/orders/${o.id}/status/`,{status:'ready'},o.id)}>{busy===o.id?t.actionInProgress:t.ready}</button>}
   {role==='captain'&&(o.status==='ready'||(o.order_type==='ride'&&o.status==='new'))&&!o.captain&&<button onClick={()=>confirmAction({title:t.accept,message:`${t.orderNumber} ${o.order_number} · ${money(o.delivery_fee)}`,confirmLabel:t.captainAcceptPrice}).then(ok=>{if(ok)act(`/orders/${o.id}/assign/`,{accepted_delivery_fee:String(o.delivery_fee)})})}>{t.captainAcceptPrice} · {money(o.delivery_fee)}</button>}
   {role==='captain'&&o.status==='assigned'&&o.order_type==='store'&&!o.merchant_arrived_at&&<button className="secondary" onClick={()=>act(`/orders/${o.id}/arrive/`,{})}>{t.arrivedStore||'وصلت إلى المتجر'}</button>}
   {role==='captain'&&o.status==='assigned'&&o.order_type==='ride'&&<button onClick={()=>act(`/orders/${o.id}/status/`,{status:'picked_up'})}>{t.pickup}</button>}
   {role==='captain'&&o.status==='assigned'&&o.merchant_arrived_at&&<><button onClick={()=>act(`/orders/${o.id}/status/`,{status:'picked_up'})}>{t.pickup}</button>{clock-new Date(o.merchant_arrived_at).getTime()>=10*60000&&<button className="secondary" onClick={()=>act('/delay-reports/',{order:o.id,details:t.merchantDelay||'تجاوز المتجر مدة الانتظار المجانية'})}>{t.merchantDelay||'إبلاغ عن تأخر المتجر'}</button>}</>}
   {role==='captain'&&o.status==='picked_up'&&<button onClick={()=>act(`/orders/${o.id}/status/`,{status:'delivering'})}>{t.startDelivery}</button>}
   {role==='captain'&&o.status==='delivering'&&<button onClick={()=>act(`/orders/${o.id}/status/`,{status:'awaiting_confirmation'},o.id)}>{t.confirmDelivery}</button>}
   {role==='captain'&&['picked_up','delivering'].includes(o.status)&&<button type="button" className="secondary" onClick={()=>setProofOrder(o)}>{t.recordProof}</button>}
   {role==='captain'&&!!(o.proofs||[]).length&&<p className="note">{t.proofRecorded}: {(o.proofs||[]).map(p=>p.kind==='pickup'?t.proofPickup:t.proofDelivery).join(' · ')}</p>}
   {role==='customer'&&<ReceiptConfirmation order={o} t={t} busy={busy===o.id} onConfirm={order=>confirmAction({title:t.confirmReceipt,message:`${t.orderNumber} ${order.order_number}`,confirmLabel:t.confirmReceipt,cancelLabel:t.back}).then(ok=>ok&&act(`/orders/${order.id}/status/`,{status:'completed'},order.id))}/>}
   <OrderActivityList order={o} t={t}/>
   {role==='customer'&&<OrderRating order={o} t={t} onSaved={reload}/>}
  </article>)}</div>
  {proofOrder&&<ProofDialog order={proofOrder} t={t} onClose={()=>setProofOrder(null)} onSaved={reload}/>}
 </>;
}


function LocationPicker({latitude,longitude,onSelect,label='حدد الموقع على الخريطة',referenceLatitude,referenceLongitude,referenceLabel='المتجر'}){
 const mapRef=useRef(null),mapInstance=useRef(null),selectedMarker=useRef(null),referenceMarker=useRef(null),onSelectRef=useRef(onSelect);
 onSelectRef.current=onSelect;
 const [query,setQuery]=useState(''),[searching,setSearching]=useState(false),[mapError,setMapError]=useState('');
 const uiLang=document.documentElement.lang||'ar';const isEn=uiLang==='en',isHe=uiLang==='he';const mapLabel=label.includes('المتجر')?(isEn?'Select the store location on the map':isHe?'בחרו את מיקום החנות במפה':label):(isEn?'Select the delivery location on the map':isHe?'בחרו את מיקום המסירה במפה':label);
 const mapWords=isEn?{search:'Search',searching:'Searching…',find:'Search for a city, street or address',current:'◎ My location',instructions:'Click the map or drag the marker to set the exact location.',gps:'Your browser does not support location.',denied:'Could not get your location. Allow location access.',delivery:'Delivery location',store:'Store location'}:isHe?{search:'חיפוש',searching:'מחפש…',find:'חיפוש עיר, רחוב או כתובת',current:'◎ המיקום שלי',instructions:'לחצו על המפה או גררו את הסמן כדי לבחור מיקום מדויק.',gps:'הדפדפן אינו תומך במיקום.',denied:'לא ניתן לקבל את המיקום. יש לאשר גישה למיקום.',delivery:'מיקום המסירה',store:'מיקום החנות'}:{search:'بحث',searching:'جارٍ البحث…',find:'ابحث عن مدينة أو شارع أو عنوان',current:'◎ موقعي الحالي',instructions:'اضغط على الخريطة أو اسحب العلامة لتحديد الموقع بدقة.',gps:'المتصفح لا يدعم تحديد الموقع.',denied:'تعذر تحديد موقعك. تأكد من السماح بإذن الموقع.',delivery:'موقع التوصيل',store:'موقع المتجر'};
 useEffect(()=>{
  if(!L||!mapRef.current||mapInstance.current)return;
;const map=L.map(mapRef.current,{scrollWheelZoom:false}).setView([31.95,35.21],12);
  createTileLayer({maxZoom:19}).addTo(map);
  map.on('click',e=>pickLocation(e.latlng.lat,e.latlng.lng));mapInstance.current=map;
  const id=setTimeout(()=>map.invalidateSize(),180);
  return()=>{clearTimeout(id);map.remove();mapInstance.current=null;selectedMarker.current=null;referenceMarker.current=null};
 },[]);
 useEffect(()=>{
 const map=mapInstance.current;if(!map)return;
  const lat=Number(latitude),lng=Number(longitude),valid=latitude!==''&&latitude!==null&&latitude!==undefined&&longitude!==''&&longitude!==null&&longitude!==undefined&&Number.isFinite(lat)&&Number.isFinite(lng);
  if(valid){if(selectedMarker.current)selectedMarker.current.setLatLng([lat,lng]);else {selectedMarker.current=L.marker([lat,lng],{draggable:true,icon:createMarkerIcon({kind:'customer',label:mapWords.delivery})}).addTo(map).bindPopup(mapWords.delivery);selectedMarker.current.on('dragend',e=>{const pt=e.target.getLatLng();pickLocation(pt.lat,pt.lng)})}}
  else if(selectedMarker.current){map.removeLayer(selectedMarker.current);selectedMarker.current=null;}
  const rlat=Number(referenceLatitude),rlng=Number(referenceLongitude),refValid=referenceLatitude!==null&&referenceLatitude!==undefined&&referenceLongitude!==null&&referenceLongitude!==undefined&&Number.isFinite(rlat)&&Number.isFinite(rlng);
  if(refValid){if(referenceMarker.current)referenceMarker.current.setLatLng([rlat,rlng]);else referenceMarker.current=L.marker([rlat,rlng],{icon:createMarkerIcon({kind:'store',label:referenceLabel})}).addTo(map).bindPopup(referenceLabel);}
  else if(referenceMarker.current){map.removeLayer(referenceMarker.current);referenceMarker.current=null;}
  const pts=[];if(valid)pts.push([lat,lng]);if(refValid)pts.push([rlat,rlng]);if(pts.length===2)map.fitBounds(pts,{padding:[35,35],maxZoom:15});else if(pts.length===1)map.setView(pts[0],15);
 },[latitude,longitude,referenceLatitude,referenceLongitude,referenceLabel]);
 const round6=v=>Math.round(v*1e6)/1e6;
 async function pickLocation(lat,lng){const la=round6(lat),ln=round6(lng);onSelectRef.current?.(la,ln,'');try{const r=await fetch(geocodeUrl(GEOCODING_REVERSE_URL,{format:'jsonv2',lat:la,lon:ln,'accept-language':uiLang}),{headers:{Accept:'application/json'}});if(r.ok){const d=await r.json();if(d?.display_name)onSelectRef.current?.(la,ln,d.display_name)}}catch{}}
 async function locate(){if(!navigator.geolocation){setMapError(mapWords.gps);return;}navigator.geolocation.getCurrentPosition(pos=>{pickLocation(pos.coords.latitude,pos.coords.longitude);mapInstance.current?.setView([pos.coords.latitude,pos.coords.longitude],16);setMapError('')},()=>setMapError(mapWords.denied),{enableHighAccuracy:true,timeout:12000});}
 async function search(e){e?.preventDefault();if(!query.trim())return;setSearching(true);setMapError('');try{const url=geocodeUrl(GEOCODING_SEARCH_URL,{format:'jsonv2',limit:1,q:query});const res=await fetch(url,{headers:{Accept:'application/json'}});if(!res.ok)throw new Error('تعذر البحث عن العنوان');const rows=await res.json();if(!rows.length)throw new Error('لم يتم العثور على العنوان');const lat=round6(Number(rows[0].lat)),lng=round6(Number(rows[0].lon));onSelectRef.current?.(lat,lng,rows[0].display_name||query);mapInstance.current?.setView([lat,lng],16);}catch(err){setMapError(err.message)}finally{setSearching(false)}}
 return <div className="location-picker"><div className="location-picker-tools"><div className="location-picker-search"><input value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();search(e)}}} placeholder={mapWords.find}/><button type="button" onClick={search} disabled={searching}>{searching?mapWords.searching:mapWords.search}</button></div><button type="button" className="secondary" onClick={locate}>{mapWords.current}</button></div><div ref={mapRef} className="location-picker-map" role="application" aria-label={mapLabel}/><p className="map-instructions">{mapLabel} — {mapWords.instructions}</p>{latitude!==''&&longitude!==''&&latitude!=null&&longitude!=null&&<small className="coordinate-readout">Latitude: {Number(latitude).toFixed(6)} · Longitude: {Number(longitude).toFixed(6)}</small>}{mapError&&<p className="error">{mapError}</p>}</div>
}

function AdminOverviewMap({stores=[],orders=[],t={}}){
 const lang=document.documentElement.lang||'ar';
 const labels=makeMapLabels(t,lang,'admin');
 const [status,setStatus]=useState('active');
 const [service,setService]=useState('all');
 const [storeId,setStoreId]=useState('all');
 const [query,setQuery]=useState('');
 const words=lang==='en'
  ?{open:'Open',closed:'Closed',all:'All',active:'Active orders',status:'Status',service:'Service',store:'Store',search:'Search order, store or captain',empty:'No locations match the current filters',legendStore:'Store',legendCustomer:'Delivery location',legendCaptain:'Captain',legendRoute:'Active route',live:'Live GPS',stale:'GPS interrupted',captains:'captains',orders:'active orders',stores:'stores',storeType:'Store',parcelType:'Parcel',rideType:'Ride'}
  :lang==='he'
   ?{open:'פתוח',closed:'סגור',all:'הכל',active:'הזמנות פעילות',status:'סטטוס',service:'שירות',store:'חנות',search:'חיפוש הזמנה, חנות או שליח',empty:'אין מיקומים התואמים למסננים',legendStore:'חנות',legendCustomer:'מיקום המסירה',legendCaptain:'שליח',legendRoute:'מסלול פעיל',live:'GPS חי',stale:'ה-GPS נותק',captains:'שליחים',orders:'הזמנות פעילות',stores:'חנויות',storeType:'חנות',parcelType:'חבילה',rideType:'נסיעה'}
   :{open:'مفتوح',closed:'مغلق',all:'الكل',active:'الطلبات النشطة',status:'الحالة',service:'الخدمة',store:'المتجر',search:'ابحث عن طلب أو متجر أو كابتن',empty:'لا توجد مواقع مطابقة للفلاتر الحالية',legendStore:'متجر',legendCustomer:'موقع التوصيل',legendCaptain:'الكابتن',legendRoute:'مسار نشط',live:'تحديث GPS مباشر',stale:'انقطع تحديث GPS',captains:'كباتن',orders:'طلبات نشطة',stores:'متاجر',storeType:'متجر',parcelType:'شحن',rideType:'توصيل'};
 const term=query.trim().toLowerCase();
 const activeOrders=orders.filter(o=>!['completed','cancelled'].includes(o.status));
 const filtered=activeOrders.filter(o=>{
  const matchesStatus=status==='all'||status==='active'||o.status===status;
  const matchesService=service==='all'||o.order_type===service;
  const matchesStore=storeId==='all'||String(o.merchant)===String(storeId);
  const haystack=[o.order_number,o.merchant_name,o.customer_name,o.captain_name,o.dropoff_address].filter(Boolean).join(' ').toLowerCase();
  return matchesStatus&&matchesService&&matchesStore&&(!term||haystack.includes(term));
 });
 const points=[],seen=new Set();
 stores.filter(s=>storeId==='all'||String(s.id)===String(storeId)).forEach(s=>{
  if(!isValidLatLng(s.latitude,s.longitude))return;
  seen.add(Number(s.latitude).toFixed(5)+','+Number(s.longitude).toFixed(5));
  points.push({id:'store-'+s.id,kind:'store',lat:s.latitude,lng:s.longitude,label:s.shop_name,sublabel:s.is_open?words.open:words.closed,popup:{title:s.shop_name,lines:[s.address,s.is_open?words.open:words.closed]}});
 });
 filtered.forEach(o=>{
  if(isValidLatLng(o.dropoff_latitude,o.dropoff_longitude)){
   const key=Number(o.dropoff_latitude).toFixed(5)+','+Number(o.dropoff_longitude).toFixed(5);
   if(!seen.has(key)){
    seen.add(key);
    points.push({id:'drop-'+o.id,kind:'customer',lat:o.dropoff_latitude,lng:o.dropoff_longitude,label:labels.order+' '+o.order_number,sublabel:o.dropoff_address||'',popup:{title:labels.order+' '+o.order_number,lines:[o.dropoff_address,o.merchant_name,statusLabel(t,o.status)]}});
   }
  }
  if(isValidLatLng(o.captain_latitude,o.captain_longitude)){
   const stale=isLocationStale(o.captain_location_updated_at);
   points.push({id:'captain-'+o.id,kind:'captain',lat:o.captain_latitude,lng:o.captain_longitude,label:o.captain_name||labels.captain,assigned:true,stale,sublabel:stale?words.stale:words.live,popup:{title:o.captain_name||labels.captain,image:o.captain_profile_image,lines:[labels.order+' '+o.order_number,o.captain_location_updated_at?labels.updated+': '+new Date(o.captain_location_updated_at).toLocaleString():null,stale?words.stale:words.live]}});
  }
 });
 const secondaryLines=filtered.slice(0,20).filter(o=>isValidLatLng(o.pickup_latitude,o.pickup_longitude)&&isValidLatLng(o.dropoff_latitude,o.dropoff_longitude)).map(o=>[[Number(o.pickup_latitude),Number(o.pickup_longitude)],[Number(o.dropoff_latitude),Number(o.dropoff_longitude)]]);
 const staleCaptains=filtered.filter(o=>o.captain_latitude!=null&&isLocationStale(o.captain_location_updated_at)).length;
 const liveCaptains=filtered.filter(o=>o.captain_latitude!=null&&!isLocationStale(o.captain_location_updated_at)).length;
 const fitKey=[status,service,storeId,term,filtered.map(o=>o.id).join(',')].join('|');
 const statusOptions=[['active',words.active],['all',words.all],['new',statusLabel(t,'new')],['accepted',statusLabel(t,'accepted')],['preparing',statusLabel(t,'preparing')],['ready',statusLabel(t,'ready')],['assigned',statusLabel(t,'assigned')],['picked_up',statusLabel(t,'picked_up')],['delivering',statusLabel(t,'delivering')],['awaiting_confirmation',statusLabel(t,'awaiting_confirmation')]];
 return <div className="admin-live-map">
  <div className="wm-filters">
   <div className="search-field"><span aria-hidden="true">⌕</span><input value={query} onChange={e=>setQuery(e.target.value)} placeholder={words.search} aria-label={words.search}/></div>
   <label className="wm-filter-field"><span>{words.status}</span><select value={status} onChange={e=>setStatus(e.target.value)}>{statusOptions.map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>
   <label className="wm-filter-field"><span>{words.service}</span><select value={service} onChange={e=>setService(e.target.value)}><option value="all">{words.all}</option><option value="store">{words.storeType}</option><option value="parcel">{words.parcelType}</option><option value="ride">{words.rideType}</option></select></label>
   <label className="wm-filter-field"><span>{words.store}</span><select value={storeId} onChange={e=>setStoreId(e.target.value)}><option value="all">{words.all}</option>{stores.map(s=><option key={s.id} value={s.id}>{s.shop_name}</option>)}</select></label>
  </div>
  <DeliveryMap points={points} secondaryLines={secondaryLines} labels={labels} height={440} cluster fitKey={fitKey}
   emptyText={words.empty}
   legend={[{kind:'store',label:words.legendStore},{kind:'customer',label:words.legendCustomer},{kind:'captain',label:words.legendCaptain},{kind:'route',label:words.legendRoute}]}/>
  <div className="map-legend"><span>{points.filter(p=>p.kind==='store').length} {words.stores}</span><span>{points.filter(p=>p.kind==='customer').length} {words.orders}</span><span>{liveCaptains} {words.live}</span>{staleCaptains>0&&<small>{staleCaptains} · {words.stale}</small>}<small>{points.filter(p=>p.kind==='captain').length} {words.captains}</small></div>
 </div>;
}

function CustomerHome({t}){
 const [merchants,setMerchants]=useState([]),[products,setProducts]=useState([]);
 const [merchant,setMerchant]=useState(''),[product,setProduct]=useState(''),[qty,setQty]=useState(1),[dropoff,setDropoff]=useState(''),[dropoffLat,setDropoffLat]=useState(''),[dropoffLng,setDropoffLng]=useState(''),[dropoffNotes,setDropoffNotes]=useState('');
 const [loading,setLoading]=useState(false),[merchantLoading,setMerchantLoading]=useState(true),[productLoading,setProductLoading]=useState(false),[productReload,setProductReload]=useState(0);
 const [error,setError]=useState(''),[merchantError,setMerchantError]=useState(''),[productError,setProductError]=useState('');
 const submitLock=useRef(false),requestKey=useRef(newRequestKey());
 const {data:orders,reload}=useLoad('/orders/');
 useEffect(()=>{
  let active=true;setMerchantLoading(true);setMerchantError('');
  api('/merchants/').then(d=>{if(active)setMerchants(Array.isArray(d)?d:(d.results||[]))})
   .catch(e=>{if(active)setMerchantError(e.message)})
   .finally(()=>{if(active)setMerchantLoading(false)});
  return()=>{active=false};
 },[]);
 useEffect(()=>{
  let active=true;
  setProducts([]);setProduct('');setProductError('');
  if(!merchant){setProductLoading(false);return()=>{active=false}};
  setProductLoading(true);
  api(`/products/?merchant=${encodeURIComponent(merchant)}`)
   .then(d=>{if(active){const rows=Array.isArray(d)?d:(d.results||[]);setProducts(rows.filter(p=>p.available!==false))}})
   .catch(e=>{if(active)setProductError(e.message)})
   .finally(()=>{if(active)setProductLoading(false)});
  return()=>{active=false};
 },[merchant,productReload]);
 const selectedProduct=products.find(p=>String(p.id)===String(product));
 const selectedMerchant=merchants.find(m=>String(m.id)===String(merchant));
 async function createOrder(e){
  e.preventDefault();if(submitLock.current)return;
  if(!merchant||!selectedProduct){setError(t.chooseProduct);return}
  if(dropoffLat===''||dropoffLng===''){setError('حدد موقع التوصيل على الخريطة أولاً.');return}
  submitLock.current=true;setLoading(true);setError('');
  try{
   await api('/orders/',{method:'POST',headers:{'Idempotency-Key':requestKey.current},body:JSON.stringify({merchant:Number(merchant),items:[{product_id:Number(product),quantity:Number(qty)}],dropoff_address:dropoff,dropoff_latitude:roundCoordinate(dropoffLat),dropoff_longitude:roundCoordinate(dropoffLng),dropoff_notes:dropoffNotes,payment_method:'cash',order_type:'store'})});
   requestKey.current=newRequestKey();setDropoff('');setDropoffLat('');setDropoffLng('');setDropoffNotes('');setProduct('');setQty(1);reload();notify(t.requestSent,'success');
  }catch(e){setError(e.message);notify(e.message,'error')}
  finally{submitLock.current=false;setLoading(false)}
 }
 return <>
  <section className="panel customer-order-panel">
   <div className="section-head"><div><h3>{t.createOrder}</h3><p>{t.chooseStoreHint}</p></div><Link className="button-like" to="/ride">🛵 {t.rideService}</Link></div>
   <form className="form-stack" onSubmit={createOrder}>
    <label>{t.chooseStore}</label>
    {merchantLoading?<p className="muted-note">{t.loadingStores}</p>:merchantError?<div className="error">{merchantError} <button type="button" className="secondary" onClick={()=>window.location.reload()}>{t.retry}</button></div>:!merchants.length?<p className="empty compact-empty">{t.noOpenStores}</p>:<div className="merchant-picker-grid">{merchants.map(m=><button type="button" key={m.id} className={`merchant-choice ${String(m.id)===merchant?'selected':''}`} aria-pressed={String(m.id)===merchant} onClick={()=>setMerchant(String(m.id))}><span className="merchant-choice-photo">{m.image?<SafeImage src={m.image} alt={m.shop_name||''}/>:<span>◈</span>}</span><span className="merchant-choice-info"><b>{m.shop_name}</b><small>{m.category}</small>{m.address&&<small>{m.address}</small>}</span></button>)}</div>}
    <div className="customer-products-heading"><label>{t.chooseProduct}</label>{merchant&&<span>{products.length} {t.availableProductsCount}</span>}</div>
    {!merchant?<p className="muted-note">{t.selectStoreFirst}</p>:productLoading?<div className="product-loading"><span className="loading-dot"/> {t.loadingProducts}</div>:productError?<div className="error">{t.productLoadFailed} {productError}<button type="button" className="secondary" onClick={()=>setProductReload(v=>v+1)}>{t.retry}</button></div>:!products.length?<p className="empty compact-empty">{t.noProductsYet}</p>:<div className="customer-product-picker">{products.map(p=><button type="button" className={`customer-product-option ${String(p.id)===product?'selected':''}`} key={p.id} aria-pressed={String(p.id)===product} onClick={()=>setProduct(String(p.id))}><span className="picker-photo">{p.image?<SafeImage src={p.image} alt={p.name||''}/>:<span>▧</span>}</span><span className="customer-product-copy"><b>{p.name}</b><small>{money(p.price)}</small>{p.description&&<span className="customer-product-description">{p.description}</span>}</span><span className="product-select-mark">{String(p.id)===product?'✓':'+'}</span></button>)}</div>}
    {selectedProduct&&<div className="selected-product-summary"><span>{t.selectedProduct}</span><b>{selectedProduct.name}</b><strong>{money(selectedProduct.price)}</strong></div>}
    <label>{t.quantity}</label><input type="number" min="1" max="50" value={qty} onChange={e=>setQty(Math.max(1,Math.min(50,Number(e.target.value)||1)))}/>
    <label>{t.deliveryAddress}</label><input value={dropoff} onChange={e=>setDropoff(e.target.value)} required placeholder={t.addressHint}/>
    <LocationPicker latitude={dropoffLat} longitude={dropoffLng} referenceLatitude={selectedMerchant?.latitude} referenceLongitude={selectedMerchant?.longitude} referenceLabel={selectedMerchant?.shop_name||'المتجر'} label="حدد موقع تسليم الطلب على الخريطة" onSelect={(lat,lng,address)=>{setDropoffLat(String(lat));setDropoffLng(String(lng));if(address)setDropoff(address)}}/>
    <label>تفاصيل إضافية للتوصيل</label><textarea rows="2" value={dropoffNotes} onChange={e=>setDropoffNotes(e.target.value)} placeholder="اسم الشارع، البناية، الطابق، أقرب معلم…"/>
    <button disabled={loading||!merchant||!product||productLoading||!dropoff.trim()||dropoffLat===''||dropoffLng===''}>{loading?t.sending:t.sendOrder}</button>
    {error&&<p className="error">{error}</p>}
   </form>
  </section>
  <section><div className="section-head"><h3>{t.myOrders}</h3></div><div className="order-grid">{orders.map(o=><article className="order-card" key={o.id}><b>{t.orderPrefix} {o.order_number}</b><span className="tag">{statusLabel(t,o.status)}</span><p>{o.merchant_name}</p><p>{money(o.total)}</p><p>{o.dropoff_address}</p></article>)}</div>{!orders.length&&<Empty t={t}/>}</section>
 </>;
}

function RideBooking({t,lang,role}){
 const [form,setForm]=useState({pickup_address:'',dropoff_address:'',pickup_latitude:'',pickup_longitude:'',dropoff_latitude:'',dropoff_longitude:'',delivery_fee:'15.00',requires_checkpoint:false});
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const submitLock=useRef(false),requestKey=useRef(newRequestKey());
 const [activePoint,setActivePoint]=useState('pickup');
 const activePointRef=useRef('pickup');
 const mapRef=useRef(null),mapInstance=useRef(null),markers=useRef({}),lastGeocodeAt=useRef(0),tRef=useRef(t),langRef=useRef(lang);
 useEffect(()=>{tRef.current=t;langRef.current=lang},[t,lang]);
 useEffect(()=>{activePointRef.current=activePoint},[activePoint]);
 const {data:orders,reload}=useLoad('/orders/');
 function field(k,v){setForm(f=>({...f,[k]:v}))}
 function setPoint(which,lat,lng,address){
  const prefix=which==='pickup'?'pickup':'dropoff';
  setForm(f=>({...f,[`${prefix}_latitude`]:String(roundCoordinate(lat)),[`${prefix}_longitude`]:String(roundCoordinate(lng)),[`${prefix}_address`]:address||f[`${prefix}_address`]|| (which==='pickup'?t.pickupSelected:t.destinationSelected)}));
 }
 async function resolveAddress(which,lat,lng){
  try{
   if(Date.now()-lastGeocodeAt.current<1100)return;
   lastGeocodeAt.current=Date.now();
   const url=geocodeUrl(GEOCODING_REVERSE_URL,{format:'jsonv2',lat,lon:lng,'accept-language':langRef.current});
   const response=await fetch(url,{headers:{Accept:'application/json'}});
   if(!response.ok)throw new Error('reverse geocoding failed');
   const data=await response.json();
   const address=data?.name||data?.display_name;
   if(address){
    const prefix=which==='pickup'?'pickup':'dropoff';
    setForm(f=>(Number(f[`${prefix}_latitude`])===Number(lat)&&Number(f[`${prefix}_longitude`])===Number(lng)?{...f,[`${prefix}_address`]:address}:f));
   }
  }catch{
   // Coordinates remain visible and the user can enter a place name manually.
  }
 }
 useEffect(()=>{
  if(!L||!mapRef.current||mapInstance.current)return;
  const map=L.map(mapRef.current).setView([31.95,35.21],13);
  createTileLayer({maxZoom:19}).addTo(map);
  map.on('click',e=>{
   const which=activePointRef.current==='pickup'?'pickup':'dropoff';
   setPoint(which,e.latlng.lat,e.latlng.lng,which==='pickup'?tRef.current.pickupSelected:tRef.current.destinationSelected);
   resolveAddress(which,e.latlng.lat,e.latlng.lng);
  });
  mapInstance.current=map;
  const resizeTimer=setTimeout(()=>map.invalidateSize(),150);
  return()=>{clearTimeout(resizeTimer);map.remove();mapInstance.current=null;markers.current={}};
 },[]);
 useEffect(()=>{
  const map=mapInstance.current;if(!map||!L)return;
  ['pickup','dropoff'].forEach(which=>{
   const lat=Number(form[`${which}_latitude`]),lng=Number(form[`${which}_longitude`]);
   if(!Number.isFinite(lat)||!Number.isFinite(lng)||!form[`${which}_latitude`]||!form[`${which}_longitude`]){if(markers.current[which]){map.removeLayer(markers.current[which]);delete markers.current[which]}return;}
   const point=[lat,lng];
   if(markers.current[which]){markers.current[which].setLatLng(point);markers.current[which].setPopupContent(which==='pickup'?t.pickup:t.destination)}
   else markers.current[which]=L.marker(point,{icon:createMarkerIcon({kind:which==='pickup'?'pickup':'dropoff',label:which==='pickup'?t.pickup:t.destination})}).addTo(map).bindPopup(which==='pickup'?t.pickup:t.destination);
  });
  const points=['pickup','dropoff'].filter(k=>form[`${k}_latitude`]!==''&&form[`${k}_longitude`]!==''&&Number.isFinite(Number(form[`${k}_latitude`]))&&Number.isFinite(Number(form[`${k}_longitude`]))).map(k=>[Number(form[`${k}_latitude`]),Number(form[`${k}_longitude`])]);
  if(points.length===1)map.setView(points[0],15);else if(points.length===2)map.fitBounds(points,{padding:[35,35]});
 },[form.pickup_latitude,form.pickup_longitude,form.dropoff_latitude,form.dropoff_longitude,t.pickup,t.destination]);
 function locate(which){
  if(!navigator.geolocation){setError(t.locationUnavailable);return}
  setActivePoint(which);
  navigator.geolocation.getCurrentPosition(pos=>{
   const lat=pos.coords.latitude,lng=pos.coords.longitude;
   setPoint(which,lat,lng,t.currentLocation);
   resolveAddress(which,lat,lng);
   mapInstance.current?.setView([lat,lng],16);setError('');
  },()=>setError(t.locationDenied),{enableHighAccuracy:true,timeout:12000});
 }
 function coordinate(which,axis,value){
  const prefix=which==='pickup'?'pickup':'dropoff';
  field(`${prefix}_${axis}`,value);
  setActivePoint(which);
 }
 function validCoordinate(which){
  const prefix=which==='pickup'?'pickup':'dropoff';
  const lat=Number(form[`${prefix}_latitude`]),lng=Number(form[`${prefix}_longitude`]);
  return form[`${prefix}_latitude`]!==''&&form[`${prefix}_longitude`]!==''&&Number.isFinite(lat)&&Number.isFinite(lng)&&lat>=-90&&lat<=90&&lng>=-180&&lng<=180;
 }
 async function submit(e){
  e.preventDefault();if(submitLock.current)return;
  if(!validCoordinate('pickup')||!validCoordinate('dropoff')){setError(t.coordinatesInvalid);return}
  submitLock.current=true;setBusy(true);setError('');setNotice('');
  try{
   const result=await api('/orders/ride/',{method:'POST',headers:{'Idempotency-Key':requestKey.current},body:JSON.stringify({...form,pickup_latitude:roundCoordinate(form.pickup_latitude),pickup_longitude:roundCoordinate(form.pickup_longitude),dropoff_latitude:roundCoordinate(form.dropoff_latitude),dropoff_longitude:roundCoordinate(form.dropoff_longitude)})});
   requestKey.current=newRequestKey();setNotice(`${t.rideCreated} #${result.order_number} · ${money(result.total)} · ${result.distance_km} km`);
   setForm({pickup_address:'',dropoff_address:'',pickup_latitude:'',pickup_longitude:'',dropoff_latitude:'',dropoff_longitude:'',delivery_fee:'15.00',requires_checkpoint:false});
   Object.values(markers.current).forEach(marker=>mapInstance.current?.removeLayer(marker));markers.current={};setActivePoint('pickup');reload();
  }catch(x){setError(x.message)}finally{submitLock.current=false;setBusy(false)}
 }
 const rides=orders.filter(o=>o.order_type==='ride');
 return <><section className="panel ride-panel"><div className="section-head ride-head"><ServiceIcon name="vespa" size="lg"/><div><h3>{t.rideTitle}</h3><p>{t.rideSubtitle}</p></div></div><form className="form-stack" onSubmit={submit}>
 <div className="ride-location-fields">
  <div className={`ride-location-card ${activePoint==='pickup'?'active':''}`}>
   <label>{t.pickupLabel}</label><input value={form.pickup_address} onFocus={()=>setActivePoint('pickup')} onChange={e=>field('pickup_address',e.target.value)} required placeholder={t.pickupPlaceholder}/>
   <button type="button" className="secondary" onClick={()=>locate('pickup')}>{t.useCurrentLocation}</button>
   <b className="coordinate-heading">{t.pickupCoordinates}</b>
   <div className="coordinate-inputs"><label>{t.latitude}<input type="number" step="any" value={form.pickup_latitude} onFocus={()=>setActivePoint('pickup')} onChange={e=>coordinate('pickup','latitude',e.target.value)} onBlur={()=>validCoordinate('pickup')&&resolveAddress('pickup',form.pickup_latitude,form.pickup_longitude)}/></label><label>{t.longitude}<input type="number" step="any" value={form.pickup_longitude} onFocus={()=>setActivePoint('pickup')} onChange={e=>coordinate('pickup','longitude',e.target.value)} onBlur={()=>validCoordinate('pickup')&&resolveAddress('pickup',form.pickup_latitude,form.pickup_longitude)}/></label></div>
   <small>{validCoordinate('pickup')?`${Number(form.pickup_latitude).toFixed(6)}, ${Number(form.pickup_longitude).toFixed(6)}`:t.selectPickup}</small>
  </div>
  <div className={`ride-location-card ${activePoint==='dropoff'?'active':''}`}>
   <label>{t.destinationLabel}</label><input value={form.dropoff_address} onFocus={()=>setActivePoint('dropoff')} onChange={e=>field('dropoff_address',e.target.value)} required placeholder={t.destinationPlaceholder}/>
   <button type="button" className="secondary" onClick={()=>locate('dropoff')}>{t.useCurrentLocation}</button>
   <b className="coordinate-heading">{t.destinationCoordinates}</b>
   <div className="coordinate-inputs"><label>{t.latitude}<input type="number" step="any" value={form.dropoff_latitude} onFocus={()=>setActivePoint('dropoff')} onChange={e=>coordinate('dropoff','latitude',e.target.value)} onBlur={()=>validCoordinate('dropoff')&&resolveAddress('dropoff',form.dropoff_latitude,form.dropoff_longitude)}/></label><label>{t.longitude}<input type="number" step="any" value={form.dropoff_longitude} onFocus={()=>setActivePoint('dropoff')} onChange={e=>coordinate('dropoff','longitude',e.target.value)} onBlur={()=>validCoordinate('dropoff')&&resolveAddress('dropoff',form.dropoff_latitude,form.dropoff_longitude)}/></label></div>
   <small>{validCoordinate('dropoff')?`${Number(form.dropoff_latitude).toFixed(6)}, ${Number(form.dropoff_longitude).toFixed(6)}`:t.selectDestination}</small>
  </div>
 </div>
 <div className="map-instructions"><b>{t.mapInstructionsTitle}</b><span>{t.mapInstructionsBody}</span><div className="map-point-switch"><button type="button" className={activePoint==='pickup'?'':'secondary'} onClick={()=>setActivePoint('pickup')}>{t.selectPickup}</button><button type="button" className={activePoint==='dropoff'?'':'secondary'} onClick={()=>setActivePoint('dropoff')}>{t.selectDestination}</button></div></div>
 <div className="ride-map" ref={mapRef} aria-label={t.mapInstructionsTitle}/>
 <label>{t.proposedDeliveryFee} (₪)<input type="number" min="0.50" max="500" step="0.50" required value={form.delivery_fee} onChange={e=>field('delivery_fee',e.target.value)}/></label>
 <p className="note">{t.ridePriceHint}</p>
 <label className="check-label"><input type="checkbox" checked={form.requires_checkpoint} onChange={e=>field('requires_checkpoint',e.target.checked)}/>{t.checkpointRoute}</label>
 <p className="note">{t.checkpointNotice}</p><p className="note">{t.ridePricingNote}</p>
 <button disabled={busy||!validCoordinate('pickup')||!validCoordinate('dropoff')}>{busy?t.sending:t.confirmRide}</button>
 {error&&<p className="error">{error}</p>}{notice&&<p className="success-note">{notice}</p>}
 </form></section>
 <section><h3 className="list-title"><ServiceIcon name="vespa" size="sm"/>{t.myRides}</h3><div className="order-grid">{rides.map(o=><article className="order-card" key={o.id}><b>{o.order_number} · {statusLabel(t,o.status)}</b><p>{o.pickup_address} → {o.dropoff_address}</p><p>{o.distance_km} km · {money(o.total)}</p>{o.captain_name&&<div className="order-person"><span className="mini-avatar">{o.captain_profile_image?<SafeImage src={o.captain_profile_image} alt={o.captain_name||''}/>:'◉'}</span>{o.captain_name}</div>}<RideRouteMap order={o} t={t} role={role}/></article>)}</div>{!rides.length&&<Empty t={t}/>}</section></>
}

function Catalog({t}){
 const {data,err,updatedAt,reload}=useLoad('/products/',(m,patch)=>{
  if(m?.type!=='stock.updated'||m.product_id==null)return;
  patch(rows=>rows.map(p=>p.id===m.product_id?{...p,quantity:m.quantity,stock_status:m.stock_status||p.stock_status}:p));
  if(m.reason==='manual')return;
  const key=m.reason==='cancel'?'stockRestoredNotice':'stockSoldNotice';
  notify(fillText(t[key],{count:Math.abs(Number(m.delta)||0),name:m.name||'',left:m.quantity}),'success');
 });
 const [form,setForm]=useState({name:'',price:'',category:'',description:'',quantity:'',low_stock_threshold:'',discount_price:'',discount_starts_at:'',discount_ends_at:''})
 const [image,setImage]=useState(null),[preview,setPreview]=useState(''),[saving,setSaving]=useState(false)
 const [query,setQuery]=useState('')
 const [editing,setEditing]=useState(null),[editForm,setEditForm]=useState({name:'',price:'',category:'',description:'',quantity:'',low_stock_threshold:'',discount_price:'',discount_starts_at:'',discount_ends_at:''}),[editImage,setEditImage]=useState(null),[editPreview,setEditPreview]=useState(''),[editBusy,setEditBusy]=useState(false)
 const [stockBusy,setStockBusy]=useState(null)
 const visible=data.filter(p=>`${p.name||''} ${p.category||''} ${p.description||''}`.toLowerCase().includes(query.trim().toLowerCase()))
 function chooseImage(file){setImage(file||null);setPreview(file?URL.createObjectURL(file):'')}
 const emptyForm={name:'',price:'',category:'',description:'',quantity:'',low_stock_threshold:'',discount_price:'',discount_starts_at:'',discount_ends_at:''};
 const promotional=v=>['quantity','low_stock_threshold','discount_price'].includes(v[0])?String(v[1]).trim()==='':(v[0].startsWith('discount_')&&!v[1]);
 async function save(e){e.preventDefault();setSaving(true);try{const fd=new FormData();Object.entries(form).forEach(([k,v])=>{if(promotional([k,v]))return;fd.append(k,v)});if(image)fd.append('image',image);await api('/products/',{method:'POST',body:fd});setForm(emptyForm);chooseImage(null);reload();notify(t.productAdded,'success')}catch(e){notify(e.message,'error')}finally{setSaving(false)}}
 async function toggle(p){try{await api(`/products/${p.id}/`,{method:'PATCH',body:JSON.stringify({available:!p.available})});reload();notify(t.productAvailabilityUpdated,'success')}catch(e){notify(e.message,'error')}}
 async function adjustStock(p,delta){if(stockBusy===p.id)return;setStockBusy(p.id);try{await api(`/products/${p.id}/stock/`,{method:'POST',body:JSON.stringify({delta})});reload();notify(t.productUpdated||t.productAdded,'success')}catch(e){notify(e.message,'error')}finally{setStockBusy(null)}}
 function startEdit(p){setEditing(p.id);setEditForm({name:p.name||'',price:String(p.price??''),category:p.category||'',description:p.description||'',quantity:p.quantity==null?'':String(p.quantity),low_stock_threshold:p.low_stock_threshold==null?'':String(p.low_stock_threshold),discount_price:p.discount_price==null?'':String(p.discount_price),discount_starts_at:(p.discount_starts_at||'').slice(0,16),discount_ends_at:(p.discount_ends_at||'').slice(0,16)});setEditImage(null);setEditPreview(p.image||'')}
 function cancelEdit(){setEditing(null);setEditImage(null);setEditPreview('')}
 async function saveEdit(e){e.preventDefault();setEditBusy(true);try{const fd=new FormData();Object.entries(editForm).forEach(([k,v])=>{if(promotional([k,v]))return;fd.append(k,v)});if(editImage)fd.append('image',editImage);await api(`/products/${editing}/`,{method:'PATCH',body:fd});cancelEdit();reload();notify(t.productUpdated||t.productAdded,'success')}catch(e){notify(e.message,'error')}finally{setEditBusy(false)}}
 async function removeProduct(p){if(!(await confirmAction({title:t.deleteProduct,message:t.deleteProductConfirm||'حذف هذا المنتج نهائياً؟',confirmLabel:t.deleteProduct,cancelLabel:t.cancel})))return;try{await api(`/products/${p.id}/`,{method:'DELETE'});if(editing===p.id)cancelEdit();reload();notify(t.productDeleted||t.productAvailabilityUpdated,'success')}catch(e){notify(e.message,'error')}}
 return <><div className="section-head"><div><h3>{t.catalog}</h3><p>{t.catalogSubtitle}</p></div><span className="count-pill">{data.length} {t.productsCount}</span><small className={`muted-note ${err?'stock-stale':''}`} role="status">{err?t.stockStale:`${t.stockLiveUpdated} ${updatedAt?new Date(updatedAt).toLocaleTimeString():'—'}`}</small></div>
 <form className="panel product-editor" onSubmit={save}><div className="editor-title"><span className="feature-icon">✦</span><div><h3>{t.addProductTitle}</h3><p>{t.addProductHint}</p></div></div>
 <div className="product-editor-grid"><div className="upload-box"><input id="product-image" type="file" accept="image/*" onChange={e=>chooseImage(e.target.files?.[0])}/><label htmlFor="product-image" className="upload-preview">{preview?<SafeImage src={preview} alt=""/>:<><span>＋</span><b>{t.uploadProductImage}</b><small>{t.imageFormats}</small></>}</label></div>
 <div className="editor-fields"><label>{t.name}<input placeholder={t.productNamePlaceholder} value={form.name} onChange={e=>setForm({...form,name:e.target.value})} required/></label><div className="two-fields"><label>{t.category}<input placeholder={t.category} value={form.category} onChange={e=>setForm({...form,category:e.target.value})}/></label><label>{t.price}<input type="number" min="0" step=".01" placeholder="0.00" value={form.price} onChange={e=>setForm({...form,price:e.target.value})} required/></label></div><div className="two-fields promo-fields"><label>{t.offerPrice}<input type="number" min="0" step=".01" placeholder={t.optional} value={form.discount_price} onChange={e=>setForm({...form,discount_price:e.target.value})}/></label><label>{t.offerStart}<input type="datetime-local" value={form.discount_starts_at} onChange={e=>setForm({...form,discount_starts_at:e.target.value})}/></label><label>{t.offerEnd}<input type="datetime-local" value={form.discount_ends_at} onChange={e=>setForm({...form,discount_ends_at:e.target.value})}/></label></div><label>{t.description}<textarea rows="3" placeholder={t.productDescriptionPlaceholder} value={form.description} onChange={e=>setForm({...form,description:e.target.value})}/></label><div className="two-fields"><label>{t.quantity}<input type="number" min="0" step="1" placeholder="0" value={form.quantity} onChange={e=>setForm({...form,quantity:e.target.value})}/></label><label>{t.lowStockThreshold}<input type="number" min="0" step="1" placeholder="5" value={form.low_stock_threshold} onChange={e=>setForm({...form,low_stock_threshold:e.target.value})}/></label></div><p className="muted-note">{t.stockHint}</p><button disabled={saving}>{saving?t.saving:t.addProduct}</button></div></div></form>
 {err&&<p className="error">{err}</p>}
 <div className="table-toolbar"><div className="search-field"><span aria-hidden="true">⌕</span><input value={query} onChange={e=>setQuery(e.target.value)} placeholder={t.searchProducts||t.search} aria-label={t.searchProducts||t.search}/></div><span className="muted-note">{visible.length} / {data.length} {t.productsCount}</span></div>
 <div className="product-grid">{visible.map(p=><article className="product-card visual-product" key={p.id}><div className="product-photo">{p.image?<SafeImage src={p.image} alt={p.name}/>:<span>▧</span>}<span className={`photo-status ${p.available?'is-available':'is-unavailable'}`}>{p.available?t.available:t.unavailable}</span></div><div className="product-info">{editing===p.id?<form className="product-edit-form" onSubmit={saveEdit}><label>{t.name}<input value={editForm.name} onChange={e=>setEditForm({...editForm,name:e.target.value})} required/></label><div className="two-fields"><label>{t.category}<input value={editForm.category} onChange={e=>setEditForm({...editForm,category:e.target.value})}/></label><label>{t.price}<input type="number" min="0" step=".01" value={editForm.price} onChange={e=>setEditForm({...editForm,price:e.target.value})} required/></label></div><div className="two-fields promo-fields"><label>{t.offerPrice}<input type="number" min="0" step=".01" placeholder={t.optional} value={editForm.discount_price} onChange={e=>setEditForm({...editForm,discount_price:e.target.value})}/></label><label>{t.offerStart}<input type="datetime-local" value={editForm.discount_starts_at} onChange={e=>setEditForm({...editForm,discount_starts_at:e.target.value})}/></label><label>{t.offerEnd}<input type="datetime-local" value={editForm.discount_ends_at} onChange={e=>setEditForm({...editForm,discount_ends_at:e.target.value})}/></label></div><label>{t.description}<textarea rows="2" value={editForm.description} onChange={e=>setEditForm({...editForm,description:e.target.value})}/></label><div className="two-fields"><label>{t.quantity}<input type="number" min="0" step="1" value={editForm.quantity} onChange={e=>setEditForm({...editForm,quantity:e.target.value})}/></label><label>{t.lowStockThreshold}<input type="number" min="0" step="1" value={editForm.low_stock_threshold} onChange={e=>setEditForm({...editForm,low_stock_threshold:e.target.value})}/></label></div><label>{t.uploadProductImage}<input type="file" accept="image/*" onChange={e=>{const f=e.target.files?.[0]||null;setEditImage(f);if(f)setEditPreview(URL.createObjectURL(f))}}/></label>{editPreview&&<div className="edit-preview"><SafeImage src={editPreview} alt={editForm.name}/></div>}<div className="edit-actions"><button disabled={editBusy}>{editBusy?t.saving:t.saveChanges}</button><button type="button" className="secondary" onClick={cancelEdit}>{t.cancel}</button></div></form>:<><small>{p.category||t.generalCategory}</small><h4>{p.name}</h4>{p.description&&<p>{p.description}</p>}<div className="product-card-bottom"><b>{money(p.price)}</b><label className="switch-row"><input type="checkbox" checked={p.available} onChange={()=>toggle(p)}/>{t.availability}</label></div><div className="product-stock"><span className={`stock-badge ${stockTone(p)}`}>{stockText(t,p)} · {typeof p.quantity==='number'?p.quantity:0}</span><div className="stock-stepper"><button type="button" className="secondary" aria-label={t.decrease} disabled={stockBusy===p.id} onClick={()=>adjustStock(p,-1)}>−</button><span>{typeof p.quantity==='number'?p.quantity:0}</span><button type="button" className="secondary" aria-label={t.increase} disabled={stockBusy===p.id} onClick={()=>adjustStock(p,1)}>＋</button></div></div><div className="product-card-actions"><button className="secondary" onClick={()=>startEdit(p)}>{t.editProduct}</button><button className="secondary" onClick={()=>removeProduct(p)}>{t.deleteProduct}</button></div></>}</div></article>)}</div>
 {!data.length&&<Empty t={t}/>}{data.length>0&&!visible.length&&<EmptyText text={t.noMatchingProducts}/>}</>
}

function AccountProfile({t,me,setMe,onSignOut,lang}){
 const [file,setFile]=useState(null),[preview,setPreview]=useState(me.profile_image||''),[error,setError]=useState(''),[notice,setNotice]=useState(''),[saving,setSaving]=useState(false);
 function choose(e){const f=e.target.files?.[0];if(!f)return;if(!['image/jpeg','image/png','image/webp'].includes(f.type)){setError(t.profileImageType);return}if(f.size>5*1024*1024){setError(t.profileImageSize);return}setError('');setNotice('');setFile(f);setPreview(URL.createObjectURL(f))}
 async function save(e){e.preventDefault();if(!file)return;setSaving(true);setError('');try{const fd=new FormData();fd.append('profile_image',file);const updated=await api('/account/profile/',{method:'PATCH',body:fd});setMe(updated);setPreview(updated.profile_image||'');setFile(null);setNotice(t.profileImageSaved)}catch(x){setError(x.message)}finally{setSaving(false)}}
 async function remove(){setSaving(true);setError('');try{const fd=new FormData();fd.append('remove_profile_image','true');const updated=await api('/account/profile/',{method:'PATCH',body:fd});setMe(updated);setPreview('');setFile(null);setNotice(t.profileImageRemoved)}catch(x){setError(x.message)}finally{setSaving(false)}}
 return <section className="panel account-profile"><div className="section-head"><div><h3>{t.accountProfile}</h3><p>{t.accountProfileHint}</p></div></div><form onSubmit={save}><div className="account-avatar-wrap"><label className="account-avatar" htmlFor="account-avatar-input">{preview?<SafeImage src={preview} alt=""/>:<span>◉</span>}<i>＋</i></label><input id="account-avatar-input" className="visually-hidden-file" type="file" accept="image/jpeg,image/png,image/webp" onChange={choose}/><div><b>{me.first_name||me.username}</b><small>{t[me.role]||me.role}</small><small>{t.profileImageHint}</small></div></div><div className="account-profile-actions"><label className="button-like" htmlFor="account-avatar-input">{t.chooseProfileImage}</label><button type="submit" disabled={!file||saving}>{saving?t.saving:t.saveProfileImage}</button>{me.profile_image&&<button type="button" className="secondary" onClick={remove} disabled={saving}>{t.removeProfileImage}</button>}</div>{error&&<p className="error">{error}</p>}{notice&&<p className="success-note">{notice}</p>}</form><NotificationToggle lang={lang}/>{onSignOut&&<button type="button" className="secondary account-signout" onClick={onSignOut}>{t.logout}</button>}</section>
}

function Profile({t,lang='ar'}){
 const [profile,setProfile]=useState(null),[logo,setLogo]=useState(null),[cover,setCover]=useState(null),[logoPreview,setLogoPreview]=useState(''),[coverPreview,setCoverPreview]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState(''),[saving,setSaving]=useState(false),[categories,setCategories]=useState([])
 useEffect(()=>{api('/merchant/profile/').then(p=>{setProfile(p);setLogoPreview(p.image||'');setCoverPreview(p.cover_image||'')}).catch(e=>setError(e.message))},[])
 useEffect(()=>{let live=true;api('/business-categories/').then(r=>{if(live)setCategories(r.categories||[])}).catch(()=>{});return()=>{live=false}},[])
 function update(k,v){setProfile(p=>({...p,[k]:v}))}
 async function save(e){e.preventDefault();setSaving(true);setError('');setNotice('');try{const fd=new FormData();['shop_name','description','category','business_category','address','opening_hours','latitude','longitude'].forEach(k=>{if(k==='business_category'&&!profile[k])return;fd.append(k,profile[k]??'')});if(logo)fd.append('image',logo);if(cover)fd.append('cover_image',cover);const r=await api('/merchant/profile/',{method:'PATCH',body:fd});setProfile(r);setLogoPreview(r.image||'');setCoverPreview(r.cover_image||'');setLogo(null);setCover(null);setNotice(t.profileSaved)}catch(e){setError(e.message)}finally{setSaving(false)}}
 if(!profile)return <section className="panel store-profile"><div className="sk-line skeleton w-40"/><div className="sk-block skeleton profile-cover-skeleton"/><div className="sk-grid">{[0,1,2,3].map(i=><div className="sk-card" key={i}/>)}</div>{error&&<p className="error">{error}</p>}</section>
 return <section className="panel store-profile"><div className="section-head"><div><h3>{t.profile}</h3><p>{t.storeProfileSubtitle}</p></div><span className="feature-icon">◉</span></div><form onSubmit={save}><div className={`cover-upload ${coverPreview?'has-image':''}`}>{coverPreview&&<SafeImage className="cover-image" src={coverPreview} alt={profile.shop_name||''}/>}<label htmlFor="store-cover">＋ {t.changeCover}</label><input id="store-cover" type="file" accept="image/*" onChange={e=>{const f=e.target.files?.[0];setCover(f||null);if(f)setCoverPreview(URL.createObjectURL(f))}}/></div><div className="store-logo-row"><label className="store-logo-upload" htmlFor="store-logo">{logoPreview?<SafeImage src={logoPreview} alt={profile.shop_name||''}/>:<span>＋</span>}<input id="store-logo" type="file" accept="image/*" onChange={e=>{const f=e.target.files?.[0];setLogo(f||null);if(f)setLogoPreview(URL.createObjectURL(f))}}/></label><div><h3>{profile.shop_name}</h3><small>{t.storeLogoHint}</small></div></div><div className="profile-fields"><label>{t.storeName}<input value={profile.shop_name||''} onChange={e=>update('shop_name',e.target.value)} required/></label><label>{t.storeCategory}<select value={profile.business_category||''} onChange={e=>{const row=categories.find(c=>String(c.id)===e.target.value);setProfile(p=>({...p,business_category:e.target.value,category:row?row.code:p.category}))}}><option value="">—</option>{categories.map(row=><option key={row.id} value={row.id}>{lang==='ar'?row.name_ar:row.name_en}</option>)}{profile.business_category&&!categories.some(c=>String(c.id)===String(profile.business_category))&&<option value={profile.business_category}>{profile.business_category_code||profile.category}</option>}</select></label><label>{t.address}<input value={profile.address||''} onChange={e=>update('address',e.target.value)}/></label><label>{t.openingHours}<input value={profile.opening_hours||''} onChange={e=>update('opening_hours',e.target.value)}/></label><label className="wide-field">{t.description}<textarea rows="4" value={profile.description||''} onChange={e=>update('description',e.target.value)}/></label></div><div className="store-location-section"><h3>{t.storeLocationTitle}</h3><p className="muted-note">{t.storeLocationHint}</p><LocationPicker latitude={profile.latitude??''} longitude={profile.longitude??''} label={t.selectStoreLocation} onSelect={(lat,lng,address)=>setProfile(p=>({...p,latitude:String(roundCoordinate(lat)),longitude:String(roundCoordinate(lng)),address:address||p.address||''}))}/></div>{error&&<p className="error">{error}</p>}{notice&&<p className="success-note">{notice}</p>}<button disabled={saving}>{saving?t.saving:t.saveProfile}</button></form></section>
}
function Reports({t}){const [report,setReport]=useState(null),[error,setError]=useState('');useEffect(()=>{let live=true;const load=()=>api('/merchant/reports/').then(x=>{if(live){setReport(x);setError('')}}).catch(e=>live&&setError(e.message));const refresh=makeCoalescedLoader(load,{minGap:2000});refresh();const id=setInterval(refresh,10000);return()=>{live=false;clearInterval(id)}},[]);const rows=uniqueRows(report?.all_orders||[]);const exportOrders=()=>exportCsv('waselni-merchant-orders.csv',[{key:'order_number',label:t.csvOrderId},{key:'status',label:t.csvStatus},{key:'merchant_name',label:t.csvMerchant},{key:'total',label:t.csvTotal},{key:'created_at',label:t.csvDate}],rows);const exportSettlements=()=>exportCsv('waselni-merchant-settlements.csv',[{key:'order_number',label:t.csvOrderId},{key:'captain_name',label:t.csvCaptain},{key:'amount',label:t.csvAmount},{key:'settled_amount',label:t.csvSettled},{key:'outstanding_amount',label:t.csvOutstanding},{key:'created_at',label:t.csvDate}],report?.cash_settlements||[]);return <><div className="section-head"><div><h3>{t.reports}</h3><p>{t.analyticsTitle||t.reports}</p></div><div className="row-actions"><button className="secondary" disabled={!rows.length} onClick={exportOrders}>{t.exportCsv}</button><button className="secondary" disabled={!report?.cash_settlements?.length} onClick={exportSettlements}>{t.exportCsv} · {t.settlements}</button></div></div>{error&&<p className="error">{error}</p>}{!report&&!error&&<div className="stats">{[0,1,2,3].map(i=><div className="stat skeleton" key={i}/>)}</div>}{report&&<><div className="stats"><Stat icon="sales" label={t.salesTodayCompleted||'مبيعات اليوم المكتملة'} value={money(report.gross_sales_today)}/><Stat icon="orders" label={t.ordersToday||t.todayOrders} value={report.orders_today}/><Stat icon="completed" label={t.completedOrders||t.completedToday} value={report.completed_today}/><Stat icon="sales" label={t.productsDue} value={money(report.cash_products_due)}/></div><p className="note">{report.net_sales_note}</p><h3>{t.orderSettlementStatus}</h3><div className="table-wrap"><table><thead><tr><th>{t.orderPrefix}</th><th>{t.captainColumn||t.captainLabel}</th><th>{t.productsAmount}</th><th>{t.productsSettled}</th><th>{t.outstandingAmount}</th><th>{t.status}</th></tr></thead><tbody>{(report.cash_settlements||[]).map(s=><tr key={s.id}><td>{s.order_number}</td><td>{s.captain_name}</td><td>{money(s.amount)}</td><td>{money(s.settled_amount)}</td><td>{money(s.outstanding_amount)}</td><td>{t[s.status]||s.status}</td></tr>)}</tbody></table></div></>}<h3>{t.orders}</h3><div className="table-wrap"><table><thead><tr><th>{t.orderPrefix}</th><th>{t.status}</th><th>{t.total}</th><th>{t.date}</th></tr></thead><tbody>{rows.map(o=><tr key={o.id}><td>{o.order_number}</td><td>{statusLabel(t,o.status)}</td><td>{money(o.total)}</td><td>{new Date(o.created_at).toLocaleDateString()}</td></tr>)}</tbody></table></div></>}
function Captain({t,lang}){
 const [profile,setProfile]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[docs,setDocs]=useState({});
 async function loadProfile(){try{const d=await api('/captains/me/');setProfile(d);setError('')}catch(e){setError(e.message)}}
 useEffect(()=>{const refresh=makeCoalescedLoader(loadProfile,{minGap:1500});refresh();const timer=setInterval(refresh,5000);const ws=orderSocket(m=>{if(m&&(m.type==='captain.eligibility'||m.type==='captain.location'))refresh()});return()=>{clearInterval(timer);if(ws)ws.close()}},[]);
 useEffect(()=>{
  if(!profile?.online||!navigator.geolocation)return;
  let lastSentAt=0,lastLat=null,lastLng=null,disposed=false;
  const watchId=navigator.geolocation.watchPosition(async position=>{
   if(disposed)return;
   const latitude=position.coords.latitude,longitude=position.coords.longitude,now=Date.now();
   const moved=lastLat==null||Math.hypot((latitude-lastLat)*111320,(longitude-lastLng)*111320*Math.cos(latitude*Math.PI/180))>=15;
   if(!moved&&now-lastSentAt<20000)return;
   if(now-lastSentAt<8000)return;
   lastSentAt=now;lastLat=latitude;lastLng=longitude;
   try{const updated=await api('/captains/me/',{method:'PATCH',body:JSON.stringify({current_latitude:roundCoordinate(latitude),current_longitude:roundCoordinate(longitude)})});if(!disposed)setProfile(current=>current?({...current,current_latitude:updated.current_latitude,current_longitude:updated.current_longitude,current_location_updated_at:updated.current_location_updated_at}):updated)}catch{}
  },()=>{if(!disposed)setError(t.locationDenied||'تعذر الوصول إلى GPS. اسمح بإذن الموقع أثناء العمل.')}, {enableHighAccuracy:true,maximumAge:5000,timeout:15000});
  return()=>{disposed=true;navigator.geolocation.clearWatch(watchId)};
 },[profile?.online,t.locationDenied]);
 async function toggle(){if(!profile)return;setBusy(true);try{const d=await api('/captains/me/',{method:'PATCH',body:JSON.stringify({online:!profile.online})});setProfile(d);setError('')}catch(e){setError(e.message);await loadProfile()}finally{setBusy(false)}}
 async function uploadDocs(e){e.preventDefault();const fd=new FormData();Object.entries(docs).forEach(([k,v])=>v&&fd.append(k,v));try{const d=await api('/captains/me/',{method:'PATCH',body:fd});setProfile(d);setDocs({});setError('');notify(t.captainDocsUploaded,'success')}catch(x){setError(x.message)}}
 async function sos(){if(!(await confirmAction({title:'SOS',message:t.sosConfirm||'هل تريد إرسال بلاغ طوارئ إلى مركز دعم وصلني؟',confirmLabel:'إرسال',cancelLabel:t.cancel||'إلغاء'})))return;let coords=t.sosUnavailable||'الموقع غير متاح';try{const pos=await new Promise((resolve,reject)=>navigator.geolocation.getCurrentPosition(resolve,reject,{enableHighAccuracy:true,timeout:10000}));coords=`${pos.coords.latitude}, ${pos.coords.longitude}`}catch{}try{await api('/support-tickets/',{method:'POST',body:JSON.stringify({subject:t.sosSubject||'بلاغ طوارئ SOS',message:`${t.sosMessage||'بلاغ طوارئ من الكابتن'} ${profile?.name||''}. ${coords}`})});notify(t.sosCreated,'success')}catch(e){setError(e.message)}}
 const e=profile?.eligibility,online=!!e?.online,documents=profile?.documents||{};
 return <><div className="section-head"><div><h3>{t.captainWorkspace}</h3><p>{t.readyOrders}</p></div><div className="row-actions"><button className="secondary" onClick={sos}>🆘 SOS</button><button disabled={busy||!e||(!online&&!e.can_go_online)} className={online?'secondary':'primary'} onClick={toggle}>{online?t.stopReceiving:t.startReceiving}</button></div></div><div className="panel">
 {e&&<>  <p>{profile.name} ({profile.username}) · {t.eligAccountId}: <b>{profile.user_id}</b> · {t.eligProfileId}: <b>{profile.captain_profile_id}</b> · {t.averageRating}: <b>{profile.rating||'—'}</b></p><EligibilityPanel e={e} t={t}/><div className={`captain-gps-status ${profile.current_location_updated_at?'is-active':''}`}><span className="gps-pulse"/><div><b>{profile.current_location_updated_at?(t.gpsSharing||'مشاركة الموقع مفعّلة'):(t.gpsWaiting||'بانتظار أول تحديث للموقع')}</b><small>{profile.current_location_updated_at?`${t.lastLocationUpdate||'آخر تحديث'}: ${new Date(profile.current_location_updated_at).toLocaleTimeString()}`:(t.gpsPermissionHint||'اسمح بالوصول للموقع أثناء العمل لعرض موقعك للزبون')}</small></div></div><div className="document-status"><b>{t.captainDocuments||'وثائق الكابتن'}</b><p>{t.identityDoc||'الهوية'}: {documents.identity_uploaded?t.uploaded:t.notUploaded} · {t.licenseDoc||'الرخصة'}: {documents.license_uploaded?t.uploaded:t.notUploaded} · {t.insuranceDoc||'التأمين'}: {documents.insurance_uploaded?t.uploaded:t.notUploaded} · {t.undertaking||'التعهد'}: {documents.undertaking_signed?t.signed:t.unsigned}</p><form className="form-stack" onSubmit={uploadDocs}><label>{t.identityDoc||'وثيقة الهوية / التصريح'}<input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={x=>setDocs(d=>({...d,identity_document:x.target.files?.[0]}))}/></label><label>{t.licenseDoc||'رخصة القيادة'}<input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={x=>setDocs(d=>({...d,driving_license_document:x.target.files?.[0]}))}/></label><label>{t.insuranceDoc||'وثيقة التأمين'}<input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={x=>setDocs(d=>({...d,insurance_document:x.target.files?.[0]}))}/></label><button disabled={!Object.values(docs).some(Boolean)}>{t.uploadDocuments||'رفع الوثائق'}</button></form></div></>}
 {error&&<p className="error">{error}</p>}</div><CaptainServicesPanel t={t} profile={profile} onChanged={loadProfile}/><CaptainSchedulePanel t={t} lang={lang}/><CaptainEarningsPanel t={t} lang={lang}/><Orders role="captain" t={t}/><ReceivedRatings t={t}/></>}

function Settlements({t,role,canManageFinance=false}){
 const [data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [captainId,setCaptainId]=useState(''),[orderIds,setOrderIds]=useState([]),[amount,setAmount]=useState('');
 const [reference,setReference]=useState(''),[notes,setNotes]=useState('');
 async function load(){
  try{setData(await api('/settlements/ledger/'));setError('')}
  catch(e){setError(e.message||t.actionFailed)}
 }
 useEffect(()=>{const refresh=makeCoalescedLoader(load,{minGap:2000});refresh();const timer=setInterval(refresh,7000);return()=>clearInterval(timer)},[]);
 useEffect(()=>{if(!captainId&&data?.captains?.length)setCaptainId(String(data.captains[0].id))},[captainId,data?.captains]);
 const availableOrders=(data?.orders||[]).filter(row=>Number(row.captain_id)===Number(captainId)&&Number(row.outstanding_amount)>0);
 const selectedOrders=availableOrders.filter(row=>orderIds.includes(row.id));
 const selectedBalance=selectedOrders.reduce((sum,row)=>sum+Number(row.outstanding_amount),0);
 async function recordReceipt(event){
  event.preventDefault();
  setBusy(true);
  try{
   await api('/settlements/receipts/',{method:'POST',body:JSON.stringify({
    captain_id:Number(captainId),order_ids:orderIds,amount,reference,notes,
   })});
   setAmount('');setReference('');setNotes('');setOrderIds([]);
   notify(t.receiptRecorded,'success');await load();
  }catch(e){setError(e.message||t.actionFailed)}
  finally{setBusy(false)}
 }
 function exportSettlementOrders(){
  exportCsv('waselni-cash-ledger.csv',[
   {key:'order_number',label:t.csvOrderId},{key:'merchant_name',label:t.csvMerchant},
   {key:'captain_name',label:t.csvCaptain},{key:'amount',label:t.csvAmount},
   {key:'settled_amount',label:t.csvSettled},{key:'outstanding_amount',label:t.csvOutstanding},
   {key:'status',label:t.csvStatus},{key:'created_at',label:t.csvDate},
  ],data?.orders||[]);
 }
 function exportReceipts(){
  exportCsv('waselni-cash-receipts.csv',[
   {key:'reference',label:t.csvReference},{key:'captain_name',label:t.csvCaptain},
   {key:'amount',label:t.csvAmount},{key:'recorded_by',label:t.csvRecordedBy},
   {key:'created_at',label:t.csvDate},{key:'notes',label:t.csvNotes},
   {value:row=>row.allocations.map(item=>`${item.order_number}: ${item.amount}`).join('; '),label:t.orders},
  ],data?.receipts||[]);
 }
 return <>
  <div className="section-head"><div><h3>{t.settlements}</h3><p>{t.settlementWorkflowHint}</p></div><div className="row-actions"><button className="secondary" disabled={!data?.orders?.length} onClick={exportSettlementOrders}>{t.exportCsv}</button><button className="secondary" disabled={!data?.receipts?.length} onClick={exportReceipts}>{t.exportCsv} · {t.transactionHistory}</button><button className="secondary" onClick={load}>{t.refresh}</button></div></div>
  {error&&<p className="error">{error}</p>}
  {data&&<div className="stats"><Stat label={t.productsDue} value={money(data.outstanding)}/><Stat label={t.productsSettled} value={money(data.total_settled)}/><Stat label={t.productsTotalDue} value={money(data.total_due)}/></div>}
  {canManageFinance&&data&&<form className="panel form-stack" onSubmit={recordReceipt}>
   <h3>{t.recordReceipt}</h3>
   <label>{t.captainName}<select required value={captainId} onChange={event=>{setCaptainId(event.target.value);setOrderIds([])}}>{data.captains.map(captain=><option key={captain.id} value={captain.id}>{captain.name}</option>)}</select></label>
   <fieldset className="form-stack"><legend>{t.selectOrders}</legend>{availableOrders.length?availableOrders.map(row=><label className="check-label" key={row.id}><input type="checkbox" checked={orderIds.includes(row.id)} onChange={event=>setOrderIds(current=>event.target.checked?[...current,row.id]:current.filter(id=>id!==row.id))}/>{t.orderPrefix} {row.order_number} · {t.outstandingAmount}: {money(row.outstanding_amount)}</label>):<p>{t.noOutstandingOrders}</p>}</fieldset>
   <p>{t.selectedOutstanding}: <b>{money(selectedBalance)}</b></p>
   <label>{t.amount}<input type="number" min="0.01" max={selectedBalance.toFixed(2)} step="0.01" value={amount} onChange={event=>setAmount(event.target.value)} required/></label>
   <label>{t.transactionReference}<input value={reference} onChange={event=>setReference(event.target.value)} maxLength={100} required/></label>
   <label>{t.notes}<textarea value={notes} onChange={event=>setNotes(event.target.value)} maxLength={500}/></label>
   <button disabled={busy||!captainId||!orderIds.length||!amount||Number(amount)>selectedBalance}>{busy?t.actionInProgress:t.recordReceipt}</button>
  </form>}
  <h3>{t.orderSettlementStatus}</h3>
  <div className="order-grid">{(data?.orders||[]).map(row=><article className="order-card" key={row.id}>
   <div className="card-top"><b>{t.orderPrefix} {row.order_number}</b><span className="tag">{t[row.status]||t.outstanding}</span></div>
   {canManageFinance&&<p>{t.captainName}: {row.captain_name}</p>}
   {role!=='merchant'&&<p>{t.merchantName}: {row.merchant_name}</p>}
   <p>{t.productsAmount}: <b>{money(row.amount)}</b></p>
   <p>{t.productsSettled}: <b>{money(row.settled_amount)}</b></p>
   <p>{t.outstandingAmount}: <b>{money(row.outstanding_amount)}</b></p>
  </article>)}</div>
  {!data?.orders?.length&&<Empty t={t}/>}
  <h3>{t.transactionHistory}</h3>
  <div className="order-grid">{(data?.receipts||[]).map(receipt=><article className="order-card" key={receipt.id}>
   <div className="card-top"><b>{receipt.reference}</b><span className="tag">{money(receipt.amount)}</span></div>
   <p>{t.captainName}: {receipt.captain_name}</p>
   {receipt.allocations.map(item=><p key={item.order_id}>{t.orderPrefix} {item.order_number}: {money(item.amount)}</p>)}
   <p>{t.recordedBy}: {receipt.recorded_by||'—'} · {new Date(receipt.created_at).toLocaleString()}</p>
   {receipt.notes&&<p className="note">{receipt.notes}</p>}
  </article>)}</div>
  {!data?.receipts?.length&&<Empty t={t}/>}
 </>;
}
const ADMIN_STATUSES=['new','accepted','preparing','ready','assigned','picked_up','delivering','awaiting_confirmation','completed','cancelled'];

function OrdersChart({rows,t}){
 const days=useMemo(()=>{const out=[],now=new Date();now.setHours(0,0,0,0);for(let i=6;i>=0;i--){const d=new Date(now);d.setDate(now.getDate()-i);out.push({key:d.toISOString().slice(0,10),label:d.toLocaleDateString(document.documentElement.lang||undefined,{weekday:'short'}),count:0})}const byKey=new Map(out.map(d=>[d.key,d]));rows.forEach(o=>{if(!o.created_at)return;const bucket=byKey.get(new Date(o.created_at).toISOString().slice(0,10));if(bucket)bucket.count+=1});return out},[rows]);
 const max=Math.max(1,...days.map(d=>d.count)),total=days.reduce((sum,d)=>sum+d.count,0);
 return <section className="chart-panel"><div className="chart-head"><div><small className="eyebrow">ANALYTICS</small><h3>{t.ordersLast7Days||'الطلبات — آخر 7 أيام'}</h3><p>{total} {t.orderCount||'طلب'}</p></div><span className="stat-icon" aria-hidden="true">▤</span></div><div className="bar-chart" role="img" aria-label={t.ordersLast7Days||'Orders in the last 7 days'}>{days.map(d=><div className="bar-col" key={d.key} title={`${d.label}: ${d.count}`}><b>{d.count}</b><div className="bar-track"><div className="bar-fill" style={{height:`${Math.max(4,(d.count/max)*100)}%`}}/></div><small>{d.label}</small></div>)}</div></section>
}

function StatusBreakdown({rows,t}){
 const counts=useMemo(()=>{const map={};ADMIN_STATUSES.forEach(s=>map[s]=0);rows.forEach(o=>{if(map[o.status]!=null)map[o.status]+=1});return map},[rows]);
 const max=Math.max(1,...Object.values(counts));
 const visible=ADMIN_STATUSES.filter(s=>counts[s]>0||['new','preparing','delivering','completed'].includes(s));
 return <section className="chart-panel"><div className="chart-head"><div><small className="eyebrow">STATUS</small><h3>{t.ordersByStatus||'الطلبات حسب الحالة'}</h3><p>{rows.length} {t.orderCount||'طلب'}</p></div></div><div className="status-breakdown">{visible.map(s=><div className="status-breakdown-row" key={s}><span>{statusLabel(t,s)}</span><div className="status-breakdown-track"><i className={`status-${s}`} style={{width:`${Math.max(3,(counts[s]/max)*100)}%`}}/></div><b>{counts[s]}</b></div>)}</div></section>
}
function Admin({t}){
 const [summary,setSummary]=useState(null),[data,setData]=useState({captains:[],merchants:[],stores:[],orders:[],tickets:[],subscriptions:[]}),[tab,setTab]=useState('overview'),[err,setErr]=useState(''),[busy,setBusy]=useState('');
 async function load(){try{const [s,o,subscriptions,stores]=await Promise.all([api('/dashboard/summary/'),api('/admin/operations/'),api('/admin/subscriptions/'),api('/admin/stores/')]);setSummary(s);setData({...o,subscriptions,stores});setErr('')}catch(e){setErr(e.message)}}
 useEffect(()=>{const refresh=makeCoalescedLoader(load,{minGap:2000});refresh();const timer=setInterval(refresh,7000);return()=>clearInterval(timer)},[]);
 async function update(kind,id,value){setBusy(`${kind}-${id}`);try{await api('/admin/operations/',{method:'PATCH',body:JSON.stringify({kind,id,value})});await load()}catch(e){setErr(e.message)}finally{setBusy('')}}
 const tabs=[['overview',t.overview],['users',t.userManagement],['subscriptions',t.subscriptionsTitle],['captains',t.captainManagement],['merchants',t.merchantManagement],['orders',t.orderManagement],['tickets',t.ticketManagement]];
 return <><div className="section-head"><div><h3>{t.dashboard}</h3><p>{t.overview} · {t.live}</p></div><button className="secondary" onClick={load}>{t.refresh}</button></div>{err&&<p className="error">{err}</p>}
 {summary&&<div className="stats"><Stat icon="orders" label={t.todayOrders} value={summary.orders_today}/><Stat icon="active" label={t.active} value={summary.active_orders}/><Stat icon="completed" label={t.completedToday} value={summary.completed_today}/><Stat icon="captains" label={t.captains} value={summary.online_captains}/><Stat icon="merchants" label={t.merchants} value={summary.open_merchants}/><Stat icon="sales" label={t.sales} value={money(summary.sales_today)}/><Stat icon="tickets" label={t.openTickets} value={summary.open_tickets}/></div>}
 <div className="admin-tabs">{tabs.map(([id,label])=><button key={id} className={tab===id?'primary':'secondary'} onClick={()=>setTab(id)}>{label}</button>)}<Link className="button-like" to="/admin">{t.controlCenter||'مركز التحكم'}</Link></div>
 {tab==='overview'&&<><div className="dashboard-split"><section className="panel"><OrdersChart rows={data.orders} t={t}/></section><section className="panel"><StatusBreakdown rows={data.orders} t={t}/></section></div><section className="panel admin-map"><h3>{t.mapTitle}</h3><p>{t.mapNote}</p><AdminOverviewMap stores={data.stores} orders={data.orders} t={t}/></section><section className="panel"><h3>{t.ordersSection}</h3><AdminOrders rows={data.orders.slice(0,8)} t={t}/></section></>}
 {tab==='users'&&<><AdminUsers t={t}/><AccountChangeAudit t={t}/><FinanceAccessAudit t={t}/></>}{tab==='subscriptions'&&<SubscriptionManagement rows={data.subscriptions} t={t} reload={load}/>}
 {tab==='captains'&&<><CaptainManagement t={t} captains={data.captains} busy={busy} update={update} reload={load}/><AdminCaptainServices t={t} onError={setErr}/></>}
 {tab==='merchants'&&<section className="panel"><h3>{t.merchantManagement}</h3>{data.stores.length?data.stores.map(m=><article className="admin-row admin-store-row" key={m.id}><div className="admin-store-head"><SafeImage src={m.image} alt={m.shop_name||''}/><div><b>{m.shop_name}</b><small>{t.owner}: {m.owner_name} · {m.username}</small><small>{m.category} · {m.address||'—'}</small><small>{t.productsCountLabel}: {m.product_count} · {new Date(m.created_at).toLocaleDateString()}</small><span className={`tag ${m.is_open?'ready':'new'}`}>{m.is_open?t.openStore:t.storeInactive}</span></div><button className="secondary" disabled={busy===`store-${m.id}`} onClick={async()=>{setBusy(`store-${m.id}`);try{await api(`/admin/stores/${m.id}/`,{method:'PATCH',body:JSON.stringify({is_open:!m.is_open})});await load()}catch(e){setErr(e.message)}finally{setBusy('')}}}>{m.is_open?t.deactivateStore:t.activateStore}</button></div>{m.cover_image&&<SafeImage className="admin-store-cover" src={m.cover_image} alt={m.shop_name||''}/>}<div className="admin-store-products">{m.products.map(p=><div key={p.id}><SafeImage src={p.image} alt={p.name||''}/><span><b>{p.name}</b><small>{money(p.price)} · {p.available?t.availableShort:t.unavailableShort}</small></span></div>)}</div></article>):<EmptyText text={t.noMerchants}/>}</section>}
 {tab==='orders'&&<section className="panel"><h3>{t.orderManagement}</h3><AdminOrders rows={data.orders} t={t}/></section>}
 {tab==='tickets'&&<section className="panel"><h3>{t.ticketManagement}</h3>{data.tickets.length?data.tickets.map(x=><article className="admin-row" key={x.id}><div><b>#{x.id} · {x.subject}</b><small>{x.username} · {new Date(x.created_at).toLocaleString()}{x.order_number?` · ${t.orderPrefix} ${x.order_number}`:''}</small><p>{x.message}</p><span className="tag">{statusLabel(t,x.status)}</span></div><select value={x.status} onChange={e=>update('ticket',x.id,e.target.value)}><option value="open">{t.open}</option><option value="in_review">{t.review}</option><option value="resolved">{t.resolve}</option></select></article>):<EmptyText text={t.noTickets}/>}</section>}
 </>}


function SubscriptionManagement({rows,t,reload}){
 const [payments,setPayments]=useState({}),[busy,setBusy]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState('');
 async function changeStatus(row,status){setBusy(`status-${row.id}`);setError('');setNotice('');try{await api(`/admin/subscriptions/${row.id}/`,{method:'PATCH',body:JSON.stringify({status})});setNotice(t.statusChanged);await reload()}catch(e){setError(e.message)}finally{setBusy('')}}
 async function record(row){const amount=payments[row.id];if(!amount)return;setBusy(`payment-${row.id}`);setError('');setNotice('');try{await api(`/admin/subscriptions/${row.id}/payments/`,{method:'POST',body:JSON.stringify({amount,method:'cash'})});setPayments(p=>({...p,[row.id]:''}));setNotice(t.paymentRecorded);await reload()}catch(e){setError(e.message)}finally{setBusy('')}}
 return <section className="panel"><div className="section-head"><div><h3>{t.subscriptionsTitle}</h3><p>{rows.length} · {t.subscriptionLedgerHint}</p></div><button className="secondary" onClick={reload}>{t.refresh}</button></div>{error&&<p className="error">{error}</p>}{notice&&<p className="success-note">{notice}</p>}{rows.length?rows.map(row=><article className="managed-user" key={row.id}><div className="managed-user-head"><div><b>{row.name}</b><small>{row.username} · ID {row.user_id} · {t[row.role]||row.role}</small><span className={`tag ${row.is_current?'ready':'new'}`}>{row.is_current?t.subscriptionCurrent:(t['subStatus_'+row.effective_status]||row.effective_status)}</span></div><label>{t.subscriptionStatus}<select value={row.status} disabled={busy===`status-${row.id}`} onChange={e=>changeStatus(row,e.target.value)}><option value="active">{t.activeSubscription}</option><option value="pending">{t.pendingSubscription}</option><option value="expired">{t.expiredSubscription}</option><option value="cancelled">{t.cancelledSubscription}</option></select></label></div><div className="subscription-summary"><div><small>{t.subscriptionPeriod}</small><b>{row.starts_on} — {row.ends_on}</b><small>{t.monthlyAmount}: {row.amount} ₪ × {row.months} {t.months}</small></div><div><small>{t.subscriptionBalance}</small><b>{row.paid_total} / {row.total_due} ₪</b><small>{t.remainingBalance}: {row.remaining} ₪</small></div></div><div className="payment-row"><input type="number" min="0.01" step="0.01" placeholder={t.paymentAmount} value={payments[row.id]??''} onChange={e=>setPayments(p=>({...p,[row.id]:e.target.value}))}/><button className="secondary" disabled={busy===`payment-${row.id}`||!payments[row.id]||Number(payments[row.id])>Number(row.remaining)} onClick={()=>record(row)}>{t.recordPayment}</button></div></article>):<EmptyText text={t.noSubscriptions}/>}</section>
}


function CaptainManagement({t,captains,busy,update,reload}){
 const [approvalBusy,setApprovalBusy]=useState(''),[approvalError,setApprovalError]=useState('');
 async function setApproval(c,status){const reason=window.prompt(t.auditReasonPrompt);if(reason===null)return;if(!reason.trim()){setApprovalError(t.auditReasonRequired);return}const key=`approval-${c.captain_profile_id}`;setApprovalBusy(key);setApprovalError('');try{await api(`/admin/captains/${c.captain_profile_id}/approval/`,{method:'POST',body:JSON.stringify({status,reason:reason.trim()})});await reload()}catch(err){setApprovalError(err.message)}finally{setApprovalBusy('')}}
 const [form,setForm]=useState({identity_number:'',first_name:'',last_name:'',phone:'',password:'',vehicle_type:'motorcycle',vehicle_model:'',plate_number:'',permit_type:'west_bank',subscription_required:true});
 const [saving,setSaving]=useState(false),[error,setError]=useState(''),[created,setCreated]=useState(null);
 function field(k,v){setForm(f=>({...f,[k]:v}))}
 async function submit(e){e.preventDefault();setSaving(true);setError('');setCreated(null);try{const result=await api('/admin/users/',{method:'POST',body:JSON.stringify({...form,role:'captain'})});setCreated(result);setForm({identity_number:'',first_name:'',last_name:'',phone:'',password:'',vehicle_type:'motorcycle',vehicle_model:'',plate_number:'',permit_type:'west_bank',subscription_required:true});await reload()}catch(e){setError(e.message)}finally{setSaving(false)}}
 return <div className="captain-admin-stack"><section className="panel"><div className="section-head"><div><h3>{t.addCaptain}</h3><p>{t.addCaptainHint}</p></div><span className="feature-icon">♧</span></div>
 <form className="user-create-form" onSubmit={submit}>
 <label>{t.identityNumber}<input value={form.identity_number} onChange={e=>field('identity_number',e.target.value)} required autoComplete="off"/></label>
 <label>{t.firstName}<input value={form.first_name} onChange={e=>field('first_name',e.target.value)} required/></label>
 <label>{t.lastName}<input value={form.last_name} onChange={e=>field('last_name',e.target.value)}/></label>
 <label>{t.phone}<input value={form.phone} onChange={e=>field('phone',e.target.value)} required/></label>
 <label>{t.temporaryPassword}<input type="password" minLength={8} value={form.password} onChange={e=>field('password',e.target.value)} placeholder={t.autoGeneratePassword}/></label>
 <div className="vehicle-type-field"><span className="field-label">{t.vehicleType}</span><div className="vehicle-choice-grid" role="group" aria-label={t.vehicleType}>{['motorcycle','car','truck'].map(v=><button type="button" key={v} className={`vehicle-choice ${form.vehicle_type===v?'is-active':''}`} onClick={()=>field('vehicle_type',v)} aria-pressed={form.vehicle_type===v}><ServiceIcon name={v} size="sm"/><span>{t[v]}</span></button>)}</div></div>
 <label>{t.vehicleModel}<input value={form.vehicle_model} onChange={e=>field('vehicle_model',e.target.value)}/></label>
 <label>{t.plateNumber}<input value={form.plate_number} onChange={e=>field('plate_number',e.target.value)}/></label>
 <label>{t.permitType}<select value={form.permit_type} onChange={e=>field('permit_type',e.target.value)}><option value="west_bank">{t.westBankPermit}</option><option value="jerusalem_id">{t.jerusalemPermit}</option><option value="work_permit">{t.workPermit}</option></select></label>
 <label className="check-label"><input type="checkbox" checked={form.subscription_required} onChange={e=>field('subscription_required',e.target.checked)}/>{t.subscriptionRequired}</label>
 <button disabled={saving}>{saving?t.saving:t.addCaptain}</button></form>
 {error&&<p className="error">{error}</p>}{created&&<div className="credential-box"><b>{t.captainCreated}</b><p>{t.loginUsername}: <strong>{created.username}</strong></p><p>{t.temporaryPassword}: <code>{created.temporary_password}</code></p><small>{t.sharePasswordWarning}</small></div>}
 </section><section className="panel"><div className="section-head"><div><h3>{t.captainManagement}</h3><p>{captains.length} · {t.captains}</p></div><button className="secondary" onClick={reload}>{t.refresh}</button></div>
 {approvalError&&<p className="error">{approvalError}</p>}{captains.length?captains.map(c=>{const e=c.eligibility,key=`approval-${c.captain_profile_id}`;return <article className="admin-row captain-row" key={c.captain_profile_id}><div><b>{c.name}</b><small>{c.username} · <ServiceIcon name={c.vehicle_type} size="sm" className="inline-svc"/>{t[c.vehicle_type]||c.vehicle_type}{c.vehicle_model?` · ${c.vehicle_model}`:''}{c.plate_number?` · ${c.plate_number}`:''}</small><small>{t.eligAccountId}: {c.user_id} · {t.eligProfileId}: {c.captain_profile_id}</small><small>{t.license}: {c.license_verified?'✓':'—'} · {t.insurance}: {c.insurance_verified?'✓':'—'}</small><small>{t.captainDocuments}: {t.identityDoc} {c.documents?.identity_uploaded?t.uploaded:t.notUploaded} · {t.licenseDoc} {c.documents?.license_uploaded?t.uploaded:t.notUploaded} · {t.insuranceDoc} {c.documents?.insurance_uploaded?t.uploaded:t.notUploaded}</small><label className="check-label"><input type="checkbox" checked={!!c.checkpoint_badge} onChange={async ev=>{try{await api(`/admin/captains/${c.captain_profile_id}/approval/`,{method:'POST',body:JSON.stringify({status:e.approval.status,checkpoint_badge:ev.target.checked})});await reload()}catch(err){setApprovalError(err.message)}}}/>{t.checkpointBadgeGrant}</label><EligibilityPanel e={e} t={t}/></div><div className="row-actions">{e.approval.status!=='approved'&&<button disabled={approvalBusy===key} onClick={()=>setApproval(c,'approved')}>{t.approve}</button>}{e.approval.status!=='rejected'&&<button className="secondary" disabled={approvalBusy===key} onClick={()=>setApproval(c,'rejected')}>{t.eligReject}</button>}{e.approval.status==='approved'&&<button className="secondary" disabled={approvalBusy===key} onClick={()=>setApproval(c,'pending')}>{t.revoke}</button>}</div></article>}):<EmptyText text={t.noCaptains}/>}
 </section></div>
}

function AdminUsers({t}){
 const [users,setUsers]=useState([]),[error,setError]=useState(''),[notice,setNotice]=useState(''),[created,setCreated]=useState(null),[busy,setBusy]=useState('');
 const [form,setForm]=useState({identity_number:'',first_name:'',last_name:'',phone:'',role:'customer',shop_name:'',subscription_required:false});
 const [plans,setPlans]=useState({}),[payments,setPayments]=useState({});
 async function load(){try{setUsers(await api('/admin/users/'));setError('')}catch(e){setError(e.message)}}
 useEffect(()=>{load()},[]);
 function setField(k,v){setForm(f=>({...f,[k]:v}))}
 async function create(e){e.preventDefault();setError('');setNotice('');setCreated(null);setBusy('create');try{const r=await api('/admin/users/',{method:'POST',body:JSON.stringify(form)});setCreated(r);setNotice(t.accountCreated);setForm({identity_number:'',first_name:'',last_name:'',phone:'',role:'customer',shop_name:'',subscription_required:false});await load()}catch(e){setError(e.message)}finally{setBusy('')}}
 async function savePlan(user){const f=plans[user.id]||{};setBusy(`plan-${user.id}`);setError('');try{await api(`/admin/users/${user.id}/subscription/`,{method:'POST',body:JSON.stringify({amount:f.amount,starts_on:f.starts_on||new Date().toISOString().slice(0,10),months:Number(f.months||1),status:'active',notes:f.notes||''})});setNotice(t.subscriptionSaved);await load()}catch(e){setError(e.message)}finally{setBusy('')}}
 async function recordPayment(user){const amount=payments[user.id];if(!user.subscription||!amount)return;setBusy(`payment-${user.id}`);setError('');try{await api(`/admin/subscriptions/${user.subscription.id}/payments/`,{method:'POST',body:JSON.stringify({amount,method:'cash'})});setNotice(t.paymentRecorded);setPayments(p=>({...p,[user.id]:''}));await load()}catch(e){setError(e.message)}finally{setBusy('')}}
 async function toggleUser(user){const reason=window.prompt(t.auditReasonPrompt);if(reason===null)return;if(!reason.trim()){setError(t.auditReasonRequired);return}setBusy(`user-${user.id}`);try{await api(`/admin/users/${user.id}/`,{method:'PATCH',body:JSON.stringify({is_active:!user.is_active,reason:reason.trim()})});await load()}catch(e){setError(e.message)}finally{setBusy('')}}
 async function toggleRequired(user){setBusy(`req-${user.id}`);try{await api(`/admin/users/${user.id}/`,{method:'PATCH',body:JSON.stringify({subscription_required:!user.subscription_required})});await load()}catch(e){setError(e.message)}finally{setBusy('')}}
 async function toggleStaff(user){setBusy(`staff-${user.id}`);try{await api(`/admin/users/${user.id}/`,{method:'PATCH',body:JSON.stringify({is_finance_staff:!user.is_finance_staff})});await load()}catch(e){setError(e.message)}finally{setBusy('')}}
 return <div className="users-admin"><section className="panel"><h3>{t.createAccount}</h3><p className="note">{t.adminCreatesAccountsNote}</p><form className="user-create-form" onSubmit={create}>
 <label>{t.identityNumber}<input value={form.identity_number} onChange={e=>setField('identity_number',e.target.value)} required autoComplete="off"/></label>
 <label>{t.firstName}<input value={form.first_name} onChange={e=>setField('first_name',e.target.value)} required/></label>
 <label>{t.lastName}<input value={form.last_name} onChange={e=>setField('last_name',e.target.value)}/></label>
 <label>{t.phone}<input value={form.phone} onChange={e=>setField('phone',e.target.value)} required/></label>
 <label>{t.accountRole}<select value={form.role} onChange={e=>{const role=e.target.value;setForm(f=>({...f,role,subscription_required:role==='merchant'||role==='captain'}))}}><option value="customer">{t.customer}</option><option value="merchant">{t.merchantRole}</option><option value="captain">{t.captainRole}</option></select></label>
 {form.role==='merchant'&&<label>{t.storeName}<input value={form.shop_name} onChange={e=>setField('shop_name',e.target.value)} required/></label>}
 <label className="check-label"><input type="checkbox" checked={form.subscription_required} onChange={e=>setField('subscription_required',e.target.checked)}/>{t.subscriptionRequired}</label>
 <button disabled={busy==='create'}>{busy==='create'?t.saving:t.createAccount}</button></form>
 {error&&<p className="error">{error}</p>}{notice&&<p className="success-note">{notice}</p>}
 {created&&<div className="credential-box"><b>{t.accountCreated}</b><p>{t.loginUsername}: <strong>{created.username}</strong></p><p>{t.temporaryPassword}: <code>{created.temporary_password}</code></p><small>{t.sharePasswordWarning}</small></div>}
 </section>
 <section className="panel"><div className="section-head"><div><h3>{t.userManagement}</h3><p>{users.length} · {t.accounts}</p></div><button className="secondary" onClick={load}>{t.refresh}</button></div>
 {users.length?users.map(u=><article className="managed-user" key={u.id}><div className="managed-user-head"><div><b>{u.name}</b><small>{u.identity_number||u.username} · {u.phone} · {t[`${u.role}Role`]||t[u.role]||u.role}</small><span className={`tag ${u.is_active?'ready':'new'}`}>{u.is_active?t.accountActive:t.accountDisabled}</span></div><button className="secondary" onClick={()=>toggleUser(u)} disabled={busy===`user-${u.id}`}>{u.is_active?t.disableAccount:t.enableAccount}</button></div>
 <label className="check-label"><input type="checkbox" checked={!!u.is_finance_staff} disabled={busy===`staff-${u.id}`} onChange={()=>toggleStaff(u)}/>{t.financeStaff}</label>
 <div className="subscription-summary"><div><small>{t.subscription}</small><b>{u.subscription?`${u.subscription.amount} ₪ / ${u.subscription.months} ${t.months}`:(u.last_subscription?`${u.last_subscription.amount} ₪ · ${t.noActiveSubscription}`:t.noSubscription)}</b><small>{u.subscription?`${u.subscription.starts_on} — ${u.subscription.ends_on}`:(u.last_subscription?`${t.lastExpiry}: ${u.last_subscription.ends_on}`:'')}</small></div><label className="check-label"><input type="checkbox" checked={u.subscription_required} onChange={()=>toggleRequired(u)} />{t.subscriptionRequired}</label></div>
 <div className="subscription-form"><b>{t.setMonthlySubscription}</b><div className="subscription-fields"><label>{t.monthlyAmount}<input type="number" min="0" step="0.01" value={plans[u.id]?.amount??''} onChange={e=>setPlans(p=>({...p,[u.id]:{...p[u.id],amount:e.target.value}}))} placeholder="0.00"/></label><label>{t.startDate}<input type="date" value={plans[u.id]?.starts_on??new Date().toISOString().slice(0,10)} onChange={e=>setPlans(p=>({...p,[u.id]:{...p[u.id],starts_on:e.target.value}}))}/></label><label>{t.durationMonths}<select value={plans[u.id]?.months??1} onChange={e=>setPlans(p=>({...p,[u.id]:{...p[u.id],months:e.target.value}}))}>{[1,2,3,6,12].map(n=><option key={n} value={n}>{n}</option>)}</select></label><button disabled={busy===`plan-${u.id}`||!plans[u.id]?.amount} onClick={()=>savePlan(u)}>{t.saveSubscription}</button></div>{u.subscription&&<div className="payment-row"><small>{t.paidSoFar}: {u.subscription.paid_total} ₪ / {u.subscription.total_due} ₪</small><input type="number" min="0.01" step="0.01" placeholder={t.paymentAmount} value={payments[u.id]??''} onChange={e=>setPayments(p=>({...p,[u.id]:e.target.value}))}/><button className="secondary" disabled={busy===`payment-${u.id}`||!payments[u.id]} onClick={()=>recordPayment(u)}>{t.recordPayment}</button></div>}</div>
 </article>):<EmptyText text={t.noUsers}/>}
 </section></div>
}
function AccountChangeAudit({t}){
 const [rows,setRows]=useState([]),[error,setError]=useState('');
 useEffect(()=>{api('/admin/account-audit/').then(setRows).catch(e=>setError(e.message))},[]);
 return <section className="panel"><div className="section-head"><div><h3>{t.accountChangeAudit}</h3><p>{t.accountChangeAuditHint}</p></div></div>{error&&<p className="error">{error}</p>}{rows.length?<div className="table-wrap"><table><thead><tr><th>{t.accountAuditTarget}</th><th>{t.status}</th><th>{t.auditReason}</th><th>{t.recordedBy}</th><th>{t.date}</th></tr></thead><tbody>{rows.map(row=><tr key={row.id}><td>{row.target}</td><td>{row.action==='captain_approval'?t.captainApprovalAudit:t.accountStatusAudit}: {t[row.previous_value]||row.previous_value} → {t[row.new_value]||row.new_value}</td><td>{row.reason}</td><td>{row.changed_by}</td><td>{new Date(row.created_at).toLocaleString()}</td></tr>)}</tbody></table></div>:!error&&<EmptyText text={t.noAccountChanges}/>}</section>
}
function FinanceAccessAudit({t}){
 const [rows,setRows]=useState([]),[error,setError]=useState('');
 useEffect(()=>{api('/admin/finance-audit/').then(setRows).catch(e=>setError(e.message))},[]);
 return <section className="panel"><div className="section-head"><div><h3>{t.financeAccessAudit}</h3><p>{t.financeAccessAuditHint}</p></div></div>{error&&<p className="error">{error}</p>}{rows.length?<div className="table-wrap"><table><thead><tr><th>{t.financeAuditUser}</th><th>{t.financeAuditPermission}</th><th>{t.recordedBy}</th><th>{t.date}</th></tr></thead><tbody>{rows.map(row=><tr key={row.id}><td>{row.user}</td><td>{row.granted?t.financeStaffGranted:t.financeStaffRevoked}</td><td>{row.changed_by}</td><td>{new Date(row.created_at).toLocaleString()}</td></tr>)}</tbody></table></div>:!error&&<EmptyText text={t.noFinanceAccessChanges}/>}</section>;
}
function AdminOrders({rows,t}){
 const [query,setQuery]=useState(''),[status,setStatus]=useState('all');
 const filtered=useMemo(()=>{const q=query.trim().toLowerCase();return rows.filter(o=>{const matchStatus=status==='all'||o.status===status;const hay=`${o.order_number||''} ${o.id} ${o.customer||''} ${o.merchant||''} ${o.captain||''} ${o.status}`.toLowerCase();return matchStatus&&(!q||hay.includes(q))})},[rows,query,status]);
 return <><div className="table-toolbar"><div className="search-field"><span aria-hidden="true">⌕</span><input value={query} onChange={e=>setQuery(e.target.value)} placeholder={t.searchOrdersHint||t.searchOrders||'ابحث برقم الطلب أو الزبون أو المتجر'} aria-label={t.searchOrders||t.search}/></div><select value={status} onChange={e=>setStatus(e.target.value)} aria-label={t.status}><option value="all">{t.allOrders||'كل الطلبات'}</option>{ADMIN_STATUSES.map(s=><option key={s} value={s}>{statusLabel(t,s)}</option>)}</select></div>{filtered.length?<div className="admin-table-wrap"><table><thead><tr><th>{t.orderPrefix}</th><th>{t.status}</th><th>{t.customerLabel}</th><th>{t.merchantLabel}</th><th>{t.captainLabel}</th><th>{t.amount}</th><th>{t.date}</th></tr></thead><tbody>{filtered.map(o=><tr key={o.id}><td>{o.order_number}</td><td>{statusLabel(t,o.status)}</td><td>{o.customer}</td><td>{o.merchant}</td><td>{o.captain}</td><td>{money(o.total)}</td><td>{new Date(o.created_at).toLocaleString()}</td></tr>)}</tbody></table></div>:<EmptyText text={t.noMatchingOrders||t.noOrders}/>}</>}
function EligibilityPanel({e,t}){
 const row=(label,value,ok)=><div className="elig-row"><small>{label}</small><span className={`tag ${ok?'ready':'bad'}`}>{value}</span></div>;
 const sub=e.subscription;
 return <div className="elig-panel"><div className="elig-grid">
  {row(t.eligAccount,e.account.active?t.eligAccountActive:t.eligAccountInactive,e.account.active)}
  {row(t.approvalStatus,t['approval_'+e.approval.status]||e.approval.status,e.approval.status==='approved')}
  {row(t.eligSubscription,t['subStatus_'+sub.status]||sub.status,sub.active)}
  {row(t.connectionStatus,e.online?t.online:t.offline,e.online)}
  <div className="elig-row"><small>{t.eligVehicle}</small><span className={`tag ${e.vehicle.valid?'ready':'bad'}`}>{e.vehicle.valid&&<ServiceIcon name={e.vehicle.type} size="sm" className="inline-svc"/>}{e.vehicle.valid?(t[e.vehicle.type]||e.vehicle.type):t.reason_vehicle_invalid}</span></div>
  <div className="elig-row"><small>{t.checkpoint}</small><span className={`tag ${e.checkpoint.badge?'ready':''}`}>{e.checkpoint.badge?t.eligBadgeYes:t.eligBadgeNo}</span></div>
 </div>
 {sub.details&&<small className="elig-dates">{sub.details.starts_on} — {sub.details.ends_on}</small>}
 <p className={e.can_receive_orders?'success-note':'note'}>{e.can_receive_orders?t.eligReceiving:`${t.eligNotReceiving}: ${t['reason_'+e.reason]||e.message||''}`}</p>
 {e.warnings.map(w=><small key={w} className="elig-dates">⚠ {t['warning_'+w]||w}</small>)}
 </div>}
function EmptyText({text}){return <div className="empty compact-empty">{text}</div>}

function Support({t}){
 const {data,reload}=useLoad('/support-tickets/');
 const {data:orders}=useLoad('/orders/');
 const [f,setF]=useState({subject:'',message:'',order:''});
 async function send(event){
  event.preventDefault();
  try{
   await api('/support-tickets/',{method:'POST',body:JSON.stringify({...f,order:f.order?Number(f.order):null})});
   setF({subject:'',message:'',order:''});reload();notify(t.supportSent,'success');
  }catch(error){notify(error.message,'error')}
 }
 return <><h3>{t.support}</h3><form className="panel form-stack" onSubmit={send}>
  <input placeholder={t.ticketTitle} value={f.subject} onChange={event=>setF({...f,subject:event.target.value})} required/>
  <textarea placeholder={t.ticketDetails} value={f.message} onChange={event=>setF({...f,message:event.target.value})} required/>
  <label>{t.supportOrder}<select value={f.order} onChange={event=>setF({...f,order:event.target.value})}><option value="">{t.noOrderLinked}</option>{orders.map(order=><option key={order.id} value={order.id}>{t.orderPrefix} {order.order_number} · {statusLabel(t,order.status)}</option>)}</select></label>
  <button>{t.sendTicket}</button>
 </form>{data.map(ticket=><div className="ticket" key={ticket.id}><b>{ticket.subject}</b><p>{ticket.message}</p><small>{statusLabel(t,ticket.status)}{ticket.order_number?` · ${t.orderPrefix} ${ticket.order_number}`:''}</small></div>)}</>;
}
function StatIcon({name}){
 const paths={
  orders:<><path d="M6 3h12a1 1 0 0 1 1 1v17l-3-2-3 2-3-2-3 2V4a1 1 0 0 1 1-1Z"/><path d="M9 8h6M9 12h6"/></>,
  active:<><circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/></>,
  completed:<><circle cx="12" cy="12" r="8"/><path d="m8.5 12 2.4 2.4L15.8 9.5"/></>,
  captains:<><circle cx="12" cy="8" r="3.4"/><path d="M5 20c0-3.5 3-5.6 7-5.6s7 2.1 7 5.6"/></>,
  merchants:<><path d="M4 9h16l-1.2-4.2A1 1 0 0 0 17.8 4H6.2a1 1 0 0 0-1 .8L4 9Z"/><path d="M5 9v10h14V9"/><path d="M9.5 19v-5h5v5"/></>,
  sales:<><rect x="3.5" y="6" width="17" height="12" rx="2.5"/><path d="M3.5 10h17"/><circle cx="12" cy="14.5" r="1.4"/></>,
  tickets:<><path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h4"/></>
 };
 return <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]||paths.orders}</svg>
}
function Stat({label,value,icon}){return <article className="stat"><div className="stat-head"><small>{label}</small>{icon&&<span className="stat-icon">{typeof icon==='string'?<StatIcon name={icon}/>:icon}</span>}</div><strong>{value}</strong></article>}
function Empty({t}){return <div className="empty"><span>✦</span><p>{t.empty}</p></div>}
export default App
