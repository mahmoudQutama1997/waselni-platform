import {useCallback,useEffect,useState} from 'react'

export const LABELS={
 ar:{title:'مركز التحكم',subtitle:'الخدمات والتجار والفروع والكباتن والعمليات والمالية',refresh:'تحديث',loading:'جارٍ التحميل…',error:'تعذر تحميل البيانات',empty:'لا توجد بيانات',search:'بحث',all:'الكل',save:'حفظ',cancel:'إلغاء',edit:'تعديل',close:'إغلاق',active:'مفعّل',inactive:'موقوف',overview:'نظرة عامة',services:'مركز الخدمات',providers:'التجار ومقدمو الخدمات',branches:'الفروع والمناطق',captains:'الكباتن',operations:'مركز العمليات',map:'الخريطة والمراقبة',analytics:'التحليلات',finance:'الإدارة المالية',staff:'الموظفون والصلاحيات',support:'الدعم والتقييمات',audit:'سجل التدقيق',notifications:'الإشعارات',settings:'الإعدادات',legacy:'الإدارة الكلاسيكية',orders:'الطلبات',sales:'المبيعات',revenue:'الإيرادات',commission:'عمولات المنصة',captainsOnline:'كباتن متصلون',merchants:'التجار',branchesCount:'الفروع',customers:'الزبائن',today:'اليوم',week:'7 أيام',month:'30 يوماً',byService:'حسب الخدمة',byRegion:'حسب المنطقة',byStatus:'حسب الحالة',status:'الحالة',service:'الخدمة',region:'المنطقة',amount:'القيمة',date:'التاريخ',name:'الاسم',nameAr:'الاسم بالعربية',nameEn:'الاسم بالإنجليزية',code:'الرمز',category:'التصنيف',workflow:'دورة العمل',pricing:'التسعير',businessType:'نوع النشاط',requirements:'متطلبات مقدم الخدمة',flow:'مراحل الطلب',hours:'ساعات العمل',regions:'المناطق',priority:'الأولوية',resolution:'الحل',assign:'إسناد',unassigned:'غير مسند',rating:'التقييم',resolve:'إغلاق التذكرة',review:'قيد المراجعة',approved:'معتمد',pending:'بانتظار المراجعة',suspended:'موقوف',rejected:'مرفوض',approve:'اعتماد',suspend:'تعليق',reject:'رفض',reason:'السبب',branch:'الفرع',provider:'التاجر',captain:'الكابتن',customer:'الزبون',total:'الإجمالي',activities:'سجل الأحداث',details:'التفاصيل',late:'متأخر',needsAttention:'يحتاج تدخلاً',completed:'مكتمل',cancelled:'ملغى',activeOrders:'قيد التنفيذ',address:'العنوان',phone:'الهاتف',coordinates:'الإحداثيات',radius:'نطاق التغطية (كم)',enable:'تفعيل',disable:'إيقاف',role:'الدور',permissions:'الصلاحيات',username:'المستخدم',password:'كلمة مرور مؤقتة',addStaff:'إضافة موظف',addRegion:'إضافة منطقة',addService:'إضافة خدمة',operational:'دورة الطلب جاهزة',notOperational:'دورة الطلب غير مبرمجة بعد',deliveryFee:'أجرة التوصيل',defaultCommission:'نسبة العمولة الافتراضية',currency:'العملة',saved:'تم الحفظ',totalOrders:'إجمالي الطلبات',avgMinutes:'متوسط زمن التنفيذ (دقيقة)',cancelRate:'معدل الإلغاء',settlements:'التسويات النقدية',outstanding:'المتبقي',receipts:'سندات القبض',subscriptions:'اشتراكات',openTickets:'تذاكر مفتوحة',alertsEmpty:'لا توجد تنبيهات حالياً',noPermission:'صلاحيتك لا تسمح بعرض هذا القسم',mapHint:'تُعرض المواقع الحقيقية المسجلة فقط؛ لا يوجد تتبع وهمي.',searchOrders:'ابحث برقم الطلب أو الزبون أو المتجر',from:'من تاريخ',to:'إلى تاريخ',apply:'تطبيق',orderFlowHint:'مراحل مفصولة بفاصلة',staffCreated:'تم إنشاء الموظف',actor:'الموظف',action:'الإجراء',target:'العنصر',before:'قبل',after:'بعد',generatePassword:'اتركه فارغاً للتوليد التلقائي',servicesHint:'الخدمات المعطلة لا تظهر للزبون ولا تُقبل طلباتها.',captainServices:'أهلية الخدمات',maxTasks:'الحد الأقصى للمهام',training:'تدريب مطلوب',documents:'الوثائق',daily:'يومي',ordersSeries:'الطلبات اليومية',revenueNote:'المبيعات = قيمة الطلبات المكتملة. إيراد المنتجات وأجرة التوصيل منفصلان، والعمولة لا تُحتسب إلا بعد ضبطها.',filterAll:'كل الحالات',newOrder:'جديد',unassignedOrders:'غير مسند',noData:'لا نتائج',add:'إضافة',editService:'تعديل الخدمة',demote:'تغيير الدور',addRegionHint:'أضف منطقة تشغيل لربط الخدمات والفروع بها.',staffHint:'الصلاحيات تُفرض في الخادم، وليس بإخفاء الأزرار فقط.',assignedTo:'مسند إلى',ticket:'التذكرة',avgRating:'متوسط التقييم',serviceOrders:'طلبات نشطة',merchantsCount:'تجار',captainsCount:'كباتن',agent:'الموظف',settingsHint:'تُستخدم هذه القيم كإعدادات اعتماد افتراضية للخدمات.',recover:'إعادة تفعيل',noAlerts:'لا شيء يحتاج انتباهك الآن.',refreshHint:'تُحدَّث الأرقام من قاعدة البيانات عند كل تحديث.'},
 en:{title:'Control center',subtitle:'Services, providers, branches, captains, operations, finance',refresh:'Refresh',loading:'Loading…',error:'Could not load data',empty:'No data',search:'Search',all:'All',save:'Save',cancel:'Cancel',edit:'Edit',close:'Close',active:'Active',inactive:'Disabled',overview:'Overview',services:'Service center',providers:'Providers',branches:'Branches & regions',captains:'Captains',operations:'Operations',map:'Live map',analytics:'Analytics',finance:'Finance',staff:'Staff & permissions',support:'Support & ratings',audit:'Audit log',notifications:'Notifications',settings:'Settings',legacy:'Classic admin',orders:'Orders',sales:'Sales',revenue:'Revenue',commission:'Commission',captainsOnline:'Captains online',merchants:'Merchants',branchesCount:'Branches',customers:'Customers',today:'Today',week:'7 days',month:'30 days',byService:'By service',byRegion:'By region',byStatus:'By status',status:'Status',service:'Service',region:'Region',amount:'Amount',date:'Date',name:'Name',nameAr:'Arabic name',nameEn:'English name',code:'Code',category:'Category',workflow:'Workflow',pricing:'Pricing',businessType:'Business type',requirements:'Provider requirements',flow:'Order flow',hours:'Working hours',regions:'Regions',priority:'Priority',resolution:'Resolution',assign:'Assign',unassigned:'Unassigned',rating:'Rating',resolve:'Resolve',review:'In review',approved:'Approved',pending:'Pending review',suspended:'Suspended',rejected:'Rejected',approve:'Approve',suspend:'Suspend',reject:'Reject',reason:'Reason',branch:'Branch',provider:'Provider',captain:'Captain',customer:'Customer',total:'Total',activities:'Activity',details:'Details',late:'Late',needsAttention:'Needs attention',completed:'Completed',cancelled:'Cancelled',activeOrders:'In progress',address:'Address',phone:'Phone',coordinates:'Coordinates',radius:'Coverage radius (km)',enable:'Enable',disable:'Disable',role:'Role',permissions:'Permissions',username:'Username',password:'Temporary password',addStaff:'Add staff',addRegion:'Add region',addService:'Add service',operational:'Order flow implemented',notOperational:'No order flow yet',deliveryFee:'Delivery fee',defaultCommission:'Default commission %',currency:'Currency',saved:'Saved',totalOrders:'Total orders',avgMinutes:'Average completion (min)',cancelRate:'Cancellation rate',settlements:'Settlements',outstanding:'Outstanding',receipts:'Receipts',subscriptions:'Subscriptions',openTickets:'Open tickets',alertsEmpty:'No alerts right now',noPermission:'Your role cannot open this section',mapHint:'Only real recorded locations are shown; no simulated tracking.',searchOrders:'Search order, customer or store',from:'From',to:'To',apply:'Apply',orderFlowHint:'Comma separated stages',staffCreated:'Staff account created',actor:'Actor',action:'Action',target:'Target',before:'Before',after:'After',generatePassword:'Leave empty to auto-generate',servicesHint:'Disabled services are hidden from customers and new orders are refused.',captainServices:'Service eligibility',maxTasks:'Active task limit',training:'Training required',documents:'Documents',daily:'Daily',ordersSeries:'Daily orders',revenueNote:'Sales are completed order totals. Product revenue and delivery fees stay separate; commission counts only after it is configured.',filterAll:'All statuses',newOrder:'New',unassignedOrders:'Unassigned',noData:'No results',add:'Add',editService:'Edit service',demote:'Change role',addRegionHint:'Add an operating region to scope services and branches.',staffHint:'Permissions are enforced by the backend, not just hidden buttons.',assignedTo:'Assigned to',ticket:'Ticket',avgRating:'Average rating',serviceOrders:'Active orders',merchantsCount:'Merchants',captainsCount:'Captains',agent:'Agent',settingsHint:'These values are the approved defaults for services.',recover:'Reactivate',noAlerts:'Nothing needs attention right now.',refreshHint:'Figures are recalculated from the database on every refresh.'},
}
LABELS.he={...LABELS.en,
 title:'מרכז השליטה',subtitle:'שירותים, ספקים, סניפים, שליחים ותפעול',refresh:'רענון',loading:'טוען…',error:'שגיאה בטעינה',empty:'אין נתונים',search:'חיפוש',save:'שמירה',cancel:'ביטול',edit:'עריכה',close:'סגירה',overview:'סקירה',services:'שירותים',providers:'ספקים',branches:'סניפים',captains:'שליחים',operations:'תפעול',map:'מפה',analytics:'אנליטיקה',finance:'כספים',staff:'צוות',support:'תמיכה',audit:'יומן ביקורת',notifications:'התראות',settings:'הגדרות',orders:'הזמנות',sales:'מכירות',status:'סטטוס',service:'שירות',region:'אזור',name:'שם',code:'קוד',category:'קטגוריה',role:'תפקיד',permissions:'הרשאות',approved:'מאושר',pending:'ממתין',suspended:'מושהה',rejected:'נדחה',active:'פעיל',inactive:'מושבת',total:'סה"כ',date:'תאריך',all:'הכל',assign:'הקצאה',reason:'סיבה',legacy:'ניהול קלאסי',legacyShort:'קלאסי'}

Object.entries({
 ar:{business:'أنواع الأنشطة',activitiesTitle:'أنواع الأنشطة التجارية',activitiesHint:'كل نشاط تجاري مرتبط بخدمة منصة، وعند اعتماد المتجر يدخل خدمته تلقائياً.',addActivity:'إضافة نشاط',activity:'نشاط المتجر',linkedService:'الخدمة المرتبطة',requiresLicense:'يتطلب ترخيصاً',merchantsCount:'متجر',noService:'بدون خدمة',activitySaved:'تم حفظ النشاط التجاري'},
 en:{business:'Business activities',activitiesTitle:'Business activities',activitiesHint:'Each business activity links to one platform service; approving a store puts it in that service automatically.',addActivity:'Add activity',activity:'Store activity',linkedService:'Linked service',requiresLicense:'Licence required',merchantsCount:'stores',noService:'No service',activitySaved:'Business activity saved'},
 he:{business:'סוגי עסקים',activitiesTitle:'סוגי עסקים',activitiesHint:'כל סוג עסק מקושר לשירות פלטפורמה; אישור חנות משייך אותה לשירות אוטומטית.',addActivity:'הוספת סוג עסק',activity:'סוג העסק',linkedService:'שירות מקושר',requiresLicense:'נדרש רישיון',merchantsCount:'חנויות',noService:'ללא שירות',activitySaved:'סוג העסק נשמר'},
}).forEach(([code,labels])=>{LABELS[code]=Object.assign(LABELS[code]||{},labels)})

Object.assign(LABELS.ar,{descriptionAr:'الوصف بالعربية',descriptionEn:'الوصف بالإنجليزية',linkedActivities:'الأنشطة المرتبطة',fulfilmentService:'الخدمة المنفّذة للطلب',fulfilmentServiceHint:'الخدمة التي تنفّذ طلبات هذا النشاط فعلياً',effectiveService:'تُنفّذ عبر',activeServices:'خدمات مفعّلة',stoppedServices:'خدمات متوقفة',serviceFlowMissing:'بلا دورة طلب — اربطها بخدمة منفّذة قبل التفعيل'})
Object.assign(LABELS.en,{descriptionAr:'Arabic description',descriptionEn:'English description',linkedActivities:'Linked activities',fulfilmentService:'Service that runs the orders',fulfilmentServiceHint:'The implemented service that actually executes orders for this activity',effectiveService:'Runs through',activeServices:'active services',stoppedServices:'stopped services',serviceFlowMissing:'No order flow — link an implemented service before enabling'})
Object.assign(LABELS.he,{descriptionAr:'תיאור בערבית',descriptionEn:'תיאור באנגלית',linkedActivities:'סוגי עסקים מקושרים',fulfilmentService:'השירות שמפעיל את ההזמנות',fulfilmentServiceHint:'השירות הפעיל שמריץ בפועל את ההזמנות של סוג העסק',effectiveService:'פועל דרך',activeServices:'שירותים פעילים',stoppedServices:'שירותים מושבתים',serviceFlowMissing:'אין תהליך הזמנה — יש לקשר שירות פעיל לפני ההפעלה'})

export const GLYPHS={
 grid:'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z',
 layers:'M12 3l9 5-9 5-9-5 9-5zM3 13l9 5 9-5',
 store:'M4 9h16l-1.2-4.2A1 1 0 0 0 17.8 4H6.2a1 1 0 0 0-1 .8L4 9zM5 9v10h14V9M9.5 19v-5h5v5',
 pin:'M12 21s7-5.6 7-11a7 7 0 1 0-14 0c0 5.4 7 11 7 11zM12 12.6a2.6 2.6 0 1 0 0-5.2 2.6 2.6 0 0 0 0 5.2z',
 scooter:'M4 17h3l3-8h4l3 8h1M6 17a2.4 2.4 0 1 1 0-.1M18 17a2.4 2.4 0 1 1 0-.1',
 orders:'M6 3h12a1 1 0 0 1 1 1v17l-3-2-3 2-3-2-3 2V4a1 1 0 0 1 1-1zM9 8h6M9 12h6',
 map:'M3 6l6-3 6 3 6-3v15l-6 3-6-3-6 3V6zM9 3v15M15 6v15',
 chart:'M4 20V4M4 20h16M7 17v-5M12 17V8M17 17v-7',
 money:'M4 6h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1zM3 10h18M12 14.5h.01',
 users:'M9 11a3.2 3.2 0 1 0 0-6.4A3.2 3.2 0 0 0 9 11zM3 20c0-3.2 2.7-5 6-5s6 1.8 6 5M16 5.5a3 3 0 0 1 0 5.8M17 15c2.4.5 4 2.2 4 5',
 support:'M4 12a8 8 0 0 1 16 0v5a2 2 0 0 1-2 2h-3M4 12v5a2 2 0 0 0 2 2h1v-7H4zM20 12v5a2 2 0 0 1-2 2h-1v-7h3z',
 shield:'M12 3L5 6v6c0 4.4 3 7.5 7 9 4-1.5 7-4.6 7-9V6l-7-3zM9 12l2 2 4-4',
 bell:'M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15L6 16zM10 20a2 2 0 0 0 4 0',
 gear:'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6L7 7M17 17l1.4 1.4M18.4 5.6L17 7M7 17l-1.4 1.4',
 logout:'M9 5H5v14h4M15 8l4 4-4 4M19 12H9',
}

export function Glyph({name,size=18}){
 return <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={GLYPHS[name]||GLYPHS.grid}/></svg>
}

export function useResource(loader,deps=[]){
 const [data,setData]=useState(null),[error,setError]=useState(''),[loading,setLoading]=useState(true)
 const load=useCallback(()=>{let live=true;setLoading(true);loader().then(rows=>{if(live){setData(rows);setError('')}}).catch(err=>{if(live)setError(err.message||'error')}).finally(()=>{if(live)setLoading(false)});return()=>{live=false}},deps)
 useEffect(()=>load(),[load])
 return {data,error,loading,reload:load}
}

export const money=value=>`${Number(value||0).toLocaleString(undefined,{maximumFractionDigits:2})} ₪`
export const when=value=>value?new Date(value).toLocaleString():'—'
export const tokenList=value=>String(value||'').split(',').map(x=>x.trim()).filter(Boolean)
export const nameOf=(row,lang)=>lang==='ar'?row.name_ar:(lang==='he'&&row.name_he)||row.name_en||row.code||row.label

export function Status({value,labels}){
 const tone=['approved','active','completed','resolved','ready','delivering'].includes(value)?'is-good':['suspended','rejected','cancelled','failed','late'].includes(value)?'is-bad':value==='pending'||value==='in_review'||value==='preparing'?'is-warn':'is-neutral'
 return <span className={`acc-pill ${tone}`}>{labels?.[value]||value}</span>
}

export function Card({title,subtitle,actions,children,className=''}){
 return <section className={`panel acc-card ${className}`}>
  {(title||actions)&&<div className="acc-card-head"><div>{title&&<h3>{title}</h3>}{subtitle&&<p className="muted-note">{subtitle}</p>}</div>{actions}</div>}
  {children}
 </section>
}

export function Field({label,children,hint}){
 return <label className="acc-field"><span>{label}</span>{children}{hint&&<small className="muted-note">{hint}</small>}</label>
}

export function Empty({text}){return <div className="empty compact-empty">{text}</div>}
export function Loader(){return <div className="stats">{[0,1,2].map(i=><div className="stat skeleton" key={i}/>)}</div>}
export function ErrorBox({text}){return text?<p className="error">{text}</p>:null}

export function KPI({label,value,icon,tone=''}){
 return <article className={`stat acc-kpi ${tone}`}><div className="stat-head"><small>{label}</small><span className="stat-icon"><Glyph name={icon} size={16}/></span></div><strong>{value}</strong></article>
}
