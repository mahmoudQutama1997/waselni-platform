import type { MapMarkerKind } from './markers'

export type MapLabels = {
  distance: string
  duration: string
  minutes: string
  meters: string
  kilometers: string
  recenter: string
  zoomIn: string
  zoomOut: string
  routeRoad: string
  routeApprox: string
  routeUnavailable: string
  live: string
  stale: string
  updated: string
  noPoints: string
  loading: string
  pickup: string
  destination: string
  store: string
  customer: string
  captain: string
  order: string
  map: string
  route: string
  clearance: string
}

type Dictionary = Record<string, unknown> | undefined

const text = (dictionary: Dictionary, key: string): string => {
  const value = dictionary?.[key]
  return typeof value === 'string' && value.trim() ? value : ''
}

const FALLBACKS: Record<'ar' | 'en' | 'he', Omit<MapLabels, 'distance' | 'duration' | 'minutes' | 'updated' | 'store' | 'customer' | 'captain' | 'pickup' | 'destination' | 'order' | 'loading'>> = {
  ar: {
    meters: 'م',
    kilometers: 'كم',
    recenter: 'إعادة تمركز الخريطة',
    zoomIn: 'تكبير',
    zoomOut: 'تصغير',
    routeRoad: 'مسار الطريق',
    routeApprox: 'مسار تقريبي — خدمة المسارات غير متاحة',
    routeUnavailable: 'تعذر حساب المسار',
    live: 'تتبع مباشر',
    stale: 'آخر موقع معروف',
    noPoints: 'لا توجد مواقع لعرضها',
    map: 'خريطة التوصيل',
    route: 'المسار',
    clearance: 'الأسعار والمسافات تقريبية حتى يبدأ التوصيل',
  },
  en: {
    meters: 'm',
    kilometers: 'km',
    recenter: 'Recenter map',
    zoomIn: 'Zoom in',
    zoomOut: 'Zoom out',
    routeRoad: 'Road route',
    routeApprox: 'Approximate line — routing unavailable',
    routeUnavailable: 'Route could not be calculated',
    live: 'Live tracking',
    stale: 'Last known location',
    noPoints: 'No locations to show',
    map: 'Delivery map',
    route: 'Route',
    clearance: 'Distances and times are estimates until delivery starts',
  },
  he: {
    meters: 'מ׳',
    kilometers: 'ק״מ',
    recenter: 'מרכוז המפה',
    zoomIn: 'הגדלה',
    zoomOut: 'הקטנה',
    routeRoad: 'מסלול בכבישים',
    routeApprox: 'קו מקורב — שירות המסלולים אינו זמין',
    routeUnavailable: 'לא ניתן לחשב מסלול',
    live: 'מעקב חי',
    stale: 'מיקום ידוע אחרון',
    noPoints: 'אין מיקומים להצגה',
    map: 'מפת משלוחים',
    route: 'מסלול',
    clearance: 'המרחקים והזמנים משוערים עד תחילת המשלוח',
  },
}

/** Localized map vocabulary, with the app dictionary taking precedence. */
export function makeMapLabels(dictionary: Dictionary, lang: 'ar' | 'en' | 'he' = 'ar', role: 'customer' | 'captain' | 'merchant' | 'admin' = 'customer'): MapLabels {
  const base = FALLBACKS[lang] ?? FALLBACKS.ar
  const words = lang === 'en'
    ? { distance: 'Distance', duration: 'ETA', minutes: 'min', updated: 'Last update', store: 'Store', customer: 'Delivery location', captain: 'Captain', pickup: 'Pickup', destination: 'Destination', order: 'Order', loading: 'Loading map data…' }
    : lang === 'he'
      ? { distance: 'מרחק', duration: 'זמן הגעה', minutes: 'דק׳', updated: 'עדכון אחרון', store: 'חנות', customer: 'מיקום המסירה', captain: 'שליח', pickup: 'איסוף', destination: 'יעד', order: 'הזמנה', loading: 'טוען נתוני מפה…' }
      : { distance: 'المسافة', duration: 'وقت الوصول', minutes: 'دقيقة', updated: 'آخر تحديث', store: 'المتجر', customer: 'موقع التوصيل', captain: 'الكابتن', pickup: 'نقطة الاستلام', destination: 'الوجهة', order: 'الطلب', loading: 'جارٍ تحميل بيانات الخريطة…' }

  return {
    ...base,
    distance: text(dictionary, 'routeDistance') || words.distance,
    duration: text(dictionary, 'routeDuration') || words.duration,
    minutes: text(dictionary, 'minutesUnit') || words.minutes,
    updated: text(dictionary, 'trackingUpdated') || words.updated,
    store: text(dictionary, 'store') || words.store,
    customer: role === 'captain' ? words.destination : (text(dictionary, 'deliveryLocation') || words.customer),
    captain: text(dictionary, 'captain') || words.captain,
    pickup: text(dictionary, 'pickup') || words.pickup,
    destination: text(dictionary, 'destination') || words.destination,
    order: text(dictionary, 'order') || words.order,
    loading: text(dictionary, 'loadingMap') || words.loading,
    live: text(dictionary, 'captainLocationLive') || base.live,
    stale: text(dictionary, 'captainLocationStale') || base.stale,
    noPoints: text(dictionary, 'routeNoCoordinates') || base.noPoints,
    recenter: text(dictionary, 'recenterMap') || base.recenter,
  }
}

export type LegendEntry = { kind: MapMarkerKind; label: string }
