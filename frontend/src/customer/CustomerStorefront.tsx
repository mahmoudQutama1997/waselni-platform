import L from '../map/leaflet';
import { useEffect, useMemo, useState, useRef } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { api, mediaUrl } from '../api';
import type { CartLine, Merchant, Order, Product } from './types';
import { MAP_TILE_URL, MAP_ATTRIBUTION, GEOCODING_REVERSE_URL, GEOCODING_SEARCH_URL, geocodeUrl } from '../config';
import Icon from '../ui/Icons.jsx';
import { EmptyState, SkeletonCards, SkeletonLines, StatusBadge } from '../ui/components.jsx';
import { markerIcon } from '../map/markers.js';

type Props = { lang: 'ar' | 'en' | 'he' };

type Copy = {
  greeting: string;
  subtitle: string;
  search: string;
  stores: string;
  all: string;
  products: string;
  add: string;
  added: string;
  unavailable: string;
  cart: string;
  empty: string;
  emptyHint: string;
  checkout: string;
  address: string;
  notes: string;
  placeOrder: string;
  cash: string;
  subtotal: string;
  total: string;
  orders: string;
  loading: string;
  retry: string;
  noStores: string;
  noProducts: string;
  searchEmpty: string;
  success: string;
  quantity: string;
  remove: string;
  open: string;
  closed: string;
  category: string;
  storeHint: string;
  cartHint: string;
  orderError: string;
  chooseStore: string;
  otherStore: string;
  clearCart: string;
  deliveryFeeNote: string;
  deliveryFee: string;
  storeLocation: string;
  customerLocation: string;
  selectLocation: string;
  useLocation: string;
  featured: string;
  topRated: string;
  nearby: string;
  nearbyHint: string;
  recentlyViewed: string;
  openNow: string;
  storesCount: string;
  openStores: string;
  rating: string;
  deliveryInfo: string;
  addressLabel: string;
  productSearch: string;
  sortRecommended: string;
  sortPriceAsc: string;
  sortPriceDesc: string;
  viewStore: string;
  trackOrder: string;
  locateMe: string;
  distance: string;
  allCategories: string;
  openingHours: string;
  searchPlaceholder: string;
  storefrontHint: string;
  statusLabels: Record<string, string>;
};

const copy: Record<Props['lang'], Copy> = {
  ar: {
    greeting: 'كل احتياجاتك، توصلك',
    subtitle: 'تسوّق من متاجر فلسطين المفضلة، وتابع طلبك لحظة بلحظة على الخريطة.',
    search: 'ابحث عن متجر...',
    stores: 'المتاجر',
    all: 'الكل',
    products: 'المنتجات',
    add: 'أضف للسلة',
    added: 'أضيف إلى السلة',
    unavailable: 'غير متوفر',
    cart: 'سلة المشتريات',
    empty: 'سلتك فارغة',
    emptyHint: 'اختر متجراً وأضف منتجات لتظهر هنا.',
    checkout: 'إتمام الطلب',
    address: 'عنوان التوصيل',
    notes: 'ملاحظات للمندوب (اختياري)',
    placeOrder: 'تأكيد الطلب',
    cash: 'الدفع نقداً عند الاستلام',
    subtotal: 'المجموع الفرعي',
    total: 'الإجمالي',
    orders: 'طلباتي الأخيرة',
    loading: 'جارٍ التحميل...',
    retry: 'إعادة المحاولة',
    noStores: 'لا توجد متاجر متاحة حالياً.',
    noProducts: 'لا توجد منتجات متاحة في هذا المتجر.',
    searchEmpty: 'لا توجد نتائج مطابقة لبحثك.',
    success: 'تم إرسال طلبك إلى المتجر بنجاح.',
    quantity: 'الكمية',
    remove: 'حذف',
    open: 'مفتوح',
    closed: 'مغلق',
    category: 'التصنيف',
    storeHint: 'اختر متجراً لعرض منتجاته',
    cartHint: 'يمكنك الطلب من متجر واحد في كل طلب.',
    orderError: 'تعذر إنشاء الطلب. حاول مرة أخرى.',
    chooseStore: 'اختر متجراً أولاً.',
    otherStore: 'سلتك تحتوي منتجات من متجر آخر. أفرغ السلة أولاً للطلب من هذا المتجر.',
    clearCart: 'إفراغ السلة',
    deliveryFeeNote: 'حدد أجرة التوصيل التي تعرض على الكابتن؛ لا تُثبت إلا بعد موافقته.',
    deliveryFee: 'أجرة التوصيل المقترحة (₪)',
    storeLocation: 'موقع المتجر',
    customerLocation: 'حدد موقع استلام الطلب على الخريطة',
    selectLocation: 'اضغط على الخريطة لتحديد موقعك أو ابحث عن عنوانك.',
    useLocation: 'استخدم موقعي',
    featured: 'متاجر مميزة',
    topRated: 'الأعلى تقييماً',
    nearby: 'قريبة منك',
    nearbyHint: 'استخدم موقعك لعرض المتاجر الأقرب إليك.',
    recentlyViewed: 'شوهدت مؤخراً',
    openNow: 'مفتوح الآن',
    storesCount: 'متجر متاح',
    openStores: 'مفتوح الآن',
    rating: 'التقييم',
    deliveryInfo: 'التوصيل متاح حسب موقع المتجر وأجرة التوصيل التي توافق عليها.',
    addressLabel: 'العنوان',
    productSearch: 'ابحث داخل المتجر...',
    sortRecommended: 'الأنسب',
    sortPriceAsc: 'الأقل سعراً',
    sortPriceDesc: 'الأعلى سعراً',
    viewStore: 'عرض المتجر',
    trackOrder: 'تتبع على الخريطة',
    locateMe: 'استخدم موقعي',
    distance: 'يبعد',
    allCategories: 'كل التصنيفات',
    openingHours: 'ساعات العمل',
    searchPlaceholder: 'ابحث باسم المتجر أو التصنيف',
    storefrontHint: 'تصفح المنتجات المتاحة وأضفها إلى سلتك.',
    statusLabels: {
      new: 'تم استلام الطلب', accepted: 'قبل المتجر الطلب', preparing: 'المتجر يجهز الطلب',
      ready: 'الطلب جاهز', assigned: 'تم تعيين كابتن', picked_up: 'تم استلام الطلب',
      delivering: 'في الطريق إليك', completed: 'تم التسليم', cancelled: 'ملغي',
    },
  },
  en: {
    greeting: 'Everything you need, delivered',
    subtitle: 'Shop your favourite Palestinian stores and follow your order live on the map.',
    search: 'Search stores...',
    stores: 'Stores',
    all: 'All',
    products: 'Products',
    add: 'Add to cart',
    added: 'Added to cart',
    unavailable: 'Unavailable',
    cart: 'Your cart',
    empty: 'Your cart is empty',
    emptyHint: 'Pick a store and add products to see them here.',
    checkout: 'Checkout',
    address: 'Delivery address',
    notes: 'Delivery notes (optional)',
    placeOrder: 'Place order',
    cash: 'Cash on delivery',
    subtotal: 'Subtotal',
    total: 'Total',
    orders: 'Recent orders',
    loading: 'Loading...',
    retry: 'Retry',
    noStores: 'No stores are available right now.',
    noProducts: 'No products available in this store.',
    searchEmpty: 'No results match your search.',
    success: 'Your order was sent to the store.',
    quantity: 'Quantity',
    remove: 'Remove',
    open: 'Open',
    closed: 'Closed',
    category: 'Category',
    storeHint: 'Choose a store to explore its products',
    cartHint: 'Orders can contain products from one store only.',
    orderError: 'Failed to place the order. Please try again.',
    chooseStore: 'Choose a store first.',
    otherStore: 'Your cart holds products from another store. Clear it first to order here.',
    clearCart: 'Clear cart',
    deliveryFeeNote: 'Set your proposed delivery fee. It becomes final only after a captain accepts it.',
    deliveryFee: 'Proposed delivery fee (₪)',
    storeLocation: 'Store location',
    customerLocation: 'Choose your delivery location on the map',
    selectLocation: 'Click the map to set your location or search for an address.',
    useLocation: 'Use my location',
    featured: 'Featured stores',
    topRated: 'Top rated',
    nearby: 'Near you',
    nearbyHint: 'Share your location to see the closest stores.',
    recentlyViewed: 'Recently viewed',
    openNow: 'Open now',
    storesCount: 'stores available',
    openStores: 'open now',
    rating: 'Rating',
    deliveryInfo: 'Delivery depends on the store location and the fee a captain accepts.',
    addressLabel: 'Address',
    productSearch: 'Search this store...',
    sortRecommended: 'Recommended',
    sortPriceAsc: 'Lowest price',
    sortPriceDesc: 'Highest price',
    viewStore: 'View store',
    trackOrder: 'Track on map',
    locateMe: 'Use my location',
    distance: 'away',
    allCategories: 'All categories',
    openingHours: 'Opening hours',
    searchPlaceholder: 'Search by store name or category',
    storefrontHint: 'Browse the available products and add them to your cart.',
    statusLabels: {
      new: 'Order received', accepted: 'Store accepted', preparing: 'Store is preparing',
      ready: 'Ready for pickup', assigned: 'Captain assigned', picked_up: 'Order picked up',
      delivering: 'On the way to you', completed: 'Delivered', cancelled: 'Cancelled',
    },
  },
  he: {
    greeting: 'כל מה שצריך, עד אליך',
    subtitle: 'קונים מהחנויות האהובות עליכם ועוקבים אחרי ההזמנה בזמן אמת במפה.',
    search: 'חיפוש חנויות...',
    stores: 'חנויות',
    all: 'הכל',
    products: 'מוצרים',
    add: 'הוספה לסל',
    added: 'נוסף לסל',
    unavailable: 'לא זמין',
    cart: 'סל הקניות',
    empty: 'סל הקניות ריק',
    emptyHint: 'בחרו חנות והוסיפו מוצרים כדי שיופיעו כאן.',
    checkout: 'לתשלום',
    address: 'כתובת למשלוח',
    notes: 'הערות לשליח (לא חובה)',
    placeOrder: 'שליחת הזמנה',
    cash: 'תשלום במזומן בעת המסירה',
    subtotal: 'סכום ביניים',
    total: 'סה״כ',
    orders: 'הזמנות אחרונות',
    loading: 'טוען...',
    retry: 'נסה שוב',
    noStores: 'אין חנויות זמינות כרגע.',
    noProducts: 'אין מוצרים זמינים בחנות זו.',
    searchEmpty: 'לא נמצאו תוצאות לחיפוש.',
    success: 'ההזמנה נשלחה לחנות.',
    quantity: 'כמות',
    remove: 'הסרה',
    open: 'פתוח',
    closed: 'סגור',
    category: 'קטגוריה',
    storeHint: 'בחרו חנות כדי לצפות במוצרים',
    cartHint: 'ניתן להזמין ממקום אחד בכל הזמנה.',
    orderError: 'לא ניתן ליצור את ההזמנה. נסו שוב.',
    chooseStore: 'יש לבחור חנות תחילה.',
    otherStore: 'בסל יש מוצרים מחנות אחרת. יש לרוקן אותו כדי להזמין כאן.',
    clearCart: 'ריקון הסל',
    deliveryFeeNote: 'קבעו דמי משלוח מוצעים. המחיר יאושר סופית רק לאחר ששליח יקבל אותו.',
    deliveryFee: 'דמי משלוח מוצעים (₪)',
    storeLocation: 'מיקום החנות',
    customerLocation: 'בחרו את מיקום המסירה במפה',
    selectLocation: 'לחצו על המפה כדי לבחור מיקום או חפשו כתובת.',
    useLocation: 'השתמשו במיקום שלי',
    featured: 'חנויות מומלצות',
    topRated: 'המדורגות ביותר',
    nearby: 'קרוב אליכם',
    nearbyHint: 'שתפו את המיקום כדי לראות את החנויות הקרובות.',
    recentlyViewed: 'נצפו לאחרונה',
    openNow: 'פתוח כעת',
    storesCount: 'חנויות זמינות',
    openStores: 'פתוחות כעת',
    rating: 'דירוג',
    deliveryInfo: 'המשלוח תלוי במיקום החנות ובדמי המשלוח שהשליח יאשר.',
    addressLabel: 'כתובת',
    productSearch: 'חיפוש בחנות...',
    sortRecommended: 'מומלץ',
    sortPriceAsc: 'המחיר הנמוך',
    sortPriceDesc: 'המחיר הגבוה',
    viewStore: 'צפייה בחנות',
    trackOrder: 'מעקב במפה',
    locateMe: 'השתמשו במיקום שלי',
    distance: 'במרחק',
    allCategories: 'כל הקטגוריות',
    openingHours: 'שעות פעילות',
    searchPlaceholder: 'חיפוש לפי שם חנות או קטגוריה',
    storefrontHint: 'עיינו במוצרים הזמינים והוסיפו אותם לסל.',
    statusLabels: {
      new: 'ההזמנה התקבלה', accepted: 'החנות אישרה', preparing: 'החנות מכינה',
      ready: 'מוכן לאיסוף', assigned: 'שליח שובץ', picked_up: 'ההזמנה נאספה',
      delivering: 'בדרך אליכם', completed: 'נמסרה', cancelled: 'בוטלה',
    },
  },
};

const money = (value: string | number) => `${Number(value || 0).toFixed(2)} ₪`;

const rows = <T,>(value: unknown): T[] =>
  Array.isArray(value) ? (value as T[]) : (((value as { results?: T[] })?.results) || []);

const readCart = (): CartLine[] => {
  try {
    return JSON.parse(localStorage.getItem('waselni_customer_cart') || '[]') as CartLine[];
  } catch {
    return [];
  }
};

const readRecent = (): number[] => {
  try {
    const parsed = JSON.parse(localStorage.getItem('waselni_recent_stores') || '[]');
    return Array.isArray(parsed) ? parsed.filter((id) => Number.isFinite(Number(id))).map(Number) : [];
  } catch {
    return [];
  }
};

/** Great-circle distance in km, used only when the customer shares a position. */
function distanceKm(a: { lat: number; lng: number }, b: { lat: number; lng: number }) {
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 6371 * 2 * Math.asin(Math.min(1, Math.sqrt(h)));
}

function hasPoint(latitude?: string | number | null, longitude?: string | number | null) {
  return (
    latitude !== null && latitude !== undefined && latitude !== '' &&
    longitude !== null && longitude !== undefined && longitude !== '' &&
    Number.isFinite(Number(latitude)) && Number.isFinite(Number(longitude))
  );
}

function CheckoutLocationMap({
  merchant, latitude, longitude, onSelect, t,
}: {
  merchant: Merchant | null;
  latitude: number | null;
  longitude: number | null;
  onSelect: (lat: number, lng: number, address?: string) => void;
  t: Copy;
}) {
  const mapRef = useRef<HTMLDivElement | null>(null);
  const mapInstance = useRef<any>(null);
  const customerMarker = useRef<any>(null);
  const storeMarker = useRef<any>(null);
  const [query, setQuery] = useState('');
  const [mapError, setMapError] = useState('');
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    if (!L || !mapRef.current || mapInstance.current) return;
    const map = L.map(mapRef.current, { scrollWheelZoom: false }).setView([31.95, 35.21], 12);
    L.tileLayer(MAP_TILE_URL, { maxZoom: 19, attribution: MAP_ATTRIBUTION }).addTo(map);
    map.on('click', (event: any) => select(event.latlng.lat, event.latlng.lng));
    mapInstance.current = map;
    const timer = window.setTimeout(() => map.invalidateSize(), 180);
    return () => {
      window.clearTimeout(timer);
      map.remove();
      mapInstance.current = null;
      customerMarker.current = null;
      storeMarker.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapInstance.current;
    if (!L || !map) return;
    if (merchant && hasPoint(merchant.latitude, merchant.longitude)) {
      const point: [number, number] = [Number(merchant.latitude), Number(merchant.longitude)];
      if (storeMarker.current) storeMarker.current.setLatLng(point);
      else
        storeMarker.current = L.marker(point, { icon: markerIcon(L, 'store') })
          .addTo(map)
          .bindPopup(merchant.shop_name);
    } else if (storeMarker.current) {
      map.removeLayer(storeMarker.current);
      storeMarker.current = null;
    }

    if (latitude != null && longitude != null) {
      const point: [number, number] = [latitude, longitude];
      if (customerMarker.current) customerMarker.current.setLatLng(point);
      else
        customerMarker.current = L.marker(point, { icon: markerIcon(L, 'customer'), draggable: true })
          .addTo(map)
          .bindPopup(t.customerLocation);
      customerMarker.current
        .off('dragend')
        .on('dragend', (event: any) => {
          const dropped = event.target.getLatLng();
          select(dropped.lat, dropped.lng);
        });
    } else if (customerMarker.current) {
      map.removeLayer(customerMarker.current);
      customerMarker.current = null;
    }

    const points: [number, number][] = [];
    if (merchant && hasPoint(merchant.latitude, merchant.longitude)) {
      points.push([Number(merchant.latitude), Number(merchant.longitude)]);
    }
    if (latitude != null && longitude != null) points.push([latitude, longitude]);
    if (points.length > 1) map.fitBounds(points, { padding: [35, 35], maxZoom: 15 });
    else if (points.length) map.setView(points[0], 15);
  }, [merchant?.latitude, merchant?.longitude, merchant?.shop_name, latitude, longitude, t.customerLocation]);

  async function select(lat: number, lng: number) {
    onSelect(lat, lng);
    try {
      const response = await fetch(
        geocodeUrl(GEOCODING_REVERSE_URL, {
          format: 'jsonv2', lat, lon: lng, 'accept-language': document.documentElement.lang || 'ar',
        })
      );
      if (response.ok) {
        const data = await response.json();
        if (data.display_name) onSelect(lat, lng, data.display_name);
      }
    } catch {
      /* Coordinates stay usable when reverse geocoding is unavailable. */
    }
  }

  async function search() {
    if (!query.trim()) return;
    setSearching(true);
    setMapError('');
    try {
      const response = await fetch(
        geocodeUrl(GEOCODING_SEARCH_URL, { format: 'jsonv2', limit: 1, q: query })
      );
      if (!response.ok) throw new Error(t.searchEmpty);
      const results = await response.json();
      if (!results.length) throw new Error(t.searchEmpty);
      const lat = Number(results[0].lat);
      const lng = Number(results[0].lon);
      onSelect(lat, lng, results[0].display_name || query);
      mapInstance.current?.setView([lat, lng], 16);
    } catch (error) {
      setMapError(error instanceof Error ? error.message : t.searchEmpty);
    } finally {
      setSearching(false);
    }
  }

  function locate() {
    if (!navigator.geolocation) {
      setMapError(t.selectLocation);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude: lat, longitude: lng } = position.coords;
        select(lat, lng);
        mapInstance.current?.setView([lat, lng], 16);
        setMapError('');
      },
      () => setMapError(t.selectLocation),
      { enableHighAccuracy: true, timeout: 12000 }
    );
  }

  return (
    <div>
      <div className="cs-map-tools">
        <div className="ds-search">
          <span className="ds-search-icon"><Icon name="search" size={16} /></span>
          <input
            className="ds-input ds-input--search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                search();
              }
            }}
            placeholder={t.address}
            aria-label={t.address}
          />
        </div>
        <button type="button" className="ds-btn ds-btn--ghost ds-btn--sm" onClick={search} disabled={searching}>
          <Icon name="search" size={14} />{searching ? t.loading : t.search.replace('...', '')}
        </button>
        <button type="button" className="ds-btn ds-btn--outline ds-btn--sm" onClick={locate}>
          <Icon name="navigation" size={14} />{t.useLocation}
        </button>
      </div>
      <div ref={mapRef} className="cs-map" role="application" aria-label={t.customerLocation} />
      <p style={{ margin: '7px 2px 0', fontSize: '11px', color: 'var(--w-muted)' }}>
        {t.selectLocation} {merchant ? `· ${t.storeLocation}: ${merchant.shop_name}` : ''}
      </p>
      {latitude != null && longitude != null && (
        <small style={{ display: 'block', marginTop: '4px', color: 'var(--w-muted)', fontSize: '10.5px' }}>
          {latitude.toFixed(6)}, {longitude.toFixed(6)}
        </small>
      )}
      {mapError && <p className="ds-alert ds-alert--error" style={{ marginTop: '7px' }}>{mapError}</p>}
    </div>
  );
}

function StoreCard({
  merchant, selected, distance, t, onSelect, compact = false,
}: {
  merchant: Merchant;
  selected: boolean;
  distance?: number | null;
  t: Copy;
  onSelect: () => void;
  compact?: boolean;
}) {
  const rating = Number(merchant.rating || 0);
  return (
    <button
      type="button"
      className={`cs-store ${selected ? 'is-selected' : ''}`}
      onClick={onSelect}
      aria-pressed={selected}
      style={compact ? undefined : undefined}
    >
      <span className="cs-store-cover">
        {merchant.cover_image || merchant.image ? (
          <img src={mediaUrl(merchant.cover_image || merchant.image || '')} alt="" loading="lazy" />
        ) : (
          <span style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', color: 'rgba(255,255,255,.75)' }}>
            <Icon name="store" size={30} />
          </span>
        )}
        <span className={`cs-store-open ${merchant.is_open ? '' : 'is-closed'}`}>
          {merchant.is_open ? t.open : t.closed}
        </span>
      </span>
      <span className="cs-store-logo">
        {merchant.image ? <img src={mediaUrl(merchant.image)} alt="" loading="lazy" /> : <Icon name="store" size={22} />}
      </span>
      <span className="cs-store-body">
        <b>{merchant.shop_name}</b>
        <span className="cs-store-meta">
          <span><Icon name="star" size={12} />{rating ? rating.toFixed(1) : '—'}</span>
          {merchant.category && <span><Icon name="tag" size={12} />{merchant.category}</span>}
          {distance != null && <span><Icon name="navigation" size={12} />{distance.toFixed(1)} {t.distance.split(' ')[0]}</span>}
        </span>
        {merchant.address && (
          <span className="cs-store-meta" style={{ color: 'var(--w-muted)' }}>
            <span><Icon name="pin" size={12} />{merchant.address}</span>
          </span>
        )}
        <span className="cs-store-tags">
          {merchant.opening_hours && <span className="ds-badge ds-badge--neutral"><Icon name="clock" size={11} />{merchant.opening_hours}</span>}
          {!hasPoint(merchant.latitude, merchant.longitude) && (
            <span className="ds-badge ds-badge--warning"><Icon name="alert" size={11} />{t.storeLocation}</span>
          )}
        </span>
      </span>
    </button>
  );
}

export default function CustomerStorefront({ lang }: Props) {
  const t = copy[lang];
  const rtl = lang !== 'en';

  const [merchants, setMerchants] = useState<Merchant[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [selectedMerchant, setSelectedMerchant] = useState<number | null>(null);
  const [cart, setCart] = useState<CartLine[]>(readCart);
  const [search, setSearch] = useState('');
  const [productQuery, setProductQuery] = useState('');
  const [sort, setSort] = useState<'recommended' | 'price_asc' | 'price_desc'>('recommended');
  const [category, setCategory] = useState('all');
  const [address, setAddress] = useState('');
  const [notes, setNotes] = useState('');
  const [dropoffLat, setDropoffLat] = useState<number | null>(null);
  const [dropoffLng, setDropoffLng] = useState<number | null>(null);
  const [deliveryFee, setDeliveryFee] = useState('10.00');
  const [loadingStores, setLoadingStores] = useState(true);
  const [loadingProducts, setLoadingProducts] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [recent, setRecent] = useState<number[]>(readRecent);
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [locating, setLocating] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoadingStores(true);
    Promise.all([api('/merchants/'), api('/orders/')])
      .then(([merchantData, orderData]) => {
        if (!alive) return;
        setMerchants(rows<Merchant>(merchantData));
        setOrders(rows<Order>(orderData).slice(0, 4));
      })
      .catch((e) => {
        if (alive) setError(e.message || t.orderError);
      })
      .finally(() => {
        if (alive) setLoadingStores(false);
      });
    return () => {
      alive = false;
    };
  }, [t.orderError]);

  useEffect(() => {
    localStorage.setItem('waselni_customer_cart', JSON.stringify(cart));
  }, [cart]);

  useEffect(() => {
    localStorage.setItem('waselni_recent_stores', JSON.stringify(recent.slice(0, 8)));
  }, [recent]);

  useEffect(() => {
    let alive = true;
    if (!selectedMerchant) {
      setProducts([]);
      return () => {
        alive = false;
      };
    }
    setLoadingProducts(true);
    api(`/products/?merchant=${selectedMerchant}`)
      .then((data) => {
        if (alive) setProducts(rows<Product>(data).filter((p) => p.available !== false));
      })
      .catch((e) => {
        if (alive) setError(e.message || t.orderError);
      })
      .finally(() => {
        if (alive) setLoadingProducts(false);
      });
    return () => {
      alive = false;
    };
  }, [selectedMerchant, t.orderError]);

  const activeMerchant = merchants.find((m) => m.id === selectedMerchant) || null;

  const categories = useMemo(() => {
    const unique = new Map<string, number>();
    for (const merchant of merchants) {
      const key = (merchant.category || '').trim();
      if (key) unique.set(key, (unique.get(key) || 0) + 1);
    }
    return [...unique.entries()].sort((a, b) => b[1] - a[1]);
  }, [merchants]);

  const filteredMerchants = useMemo(() => {
    const query = search.trim().toLowerCase();
    return merchants.filter((merchant) => {
      const matchesQuery = !query || `${merchant.shop_name} ${merchant.category || ''}`.toLowerCase().includes(query);
      const matchesCategory = category === 'all' || merchant.category === category;
      return matchesQuery && matchesCategory;
    });
  }, [merchants, search, category]);

  const ratingOf = (merchant: Merchant) => Number(merchant.rating || 0);

  const featured = useMemo(
    () => merchants.filter((m) => m.is_open && ratingOf(m) >= 4.5).sort((a, b) => ratingOf(b) - ratingOf(a)).slice(0, 6),
    [merchants]
  );

  const topRated = useMemo(
    () => [...merchants].sort((a, b) => ratingOf(b) - ratingOf(a)).slice(0, 6),
    [merchants]
  );

  const nearby = useMemo(() => {
    if (!coords) return [];
    return merchants
      .filter((m) => hasPoint(m.latitude, m.longitude))
      .map((merchant) => ({
        merchant,
        distance: distanceKm(coords, { lat: Number(merchant.latitude), lng: Number(merchant.longitude) }),
      }))
      .sort((a, b) => a.distance - b.distance)
      .slice(0, 6);
  }, [merchants, coords]);

  const recentMerchants = useMemo(
    () => recent.map((id) => merchants.find((m) => m.id === id)).filter((m): m is Merchant => Boolean(m)).slice(0, 6),
    [recent, merchants]
  );

  const filteredProducts = useMemo(() => {
    const query = productQuery.trim().toLowerCase();
    const list = products.filter((p) => !query || `${p.name} ${p.category || ''}`.toLowerCase().includes(query));
    if (sort === 'price_asc') return [...list].sort((a, b) => Number(a.price) - Number(b.price));
    if (sort === 'price_desc') return [...list].sort((a, b) => Number(b.price) - Number(a.price));
    return list;
  }, [products, productQuery, sort]);

  const subtotal = cart.reduce((sum, line) => sum + Number(line.product.price) * line.quantity, 0);
  const cartCount = cart.reduce((sum, line) => sum + line.quantity, 0);
  const openCount = merchants.filter((m) => m.is_open).length;

  function selectMerchant(id: number) {
    setSelectedMerchant(id);
    setError('');
    setProductQuery('');
    setRecent((current) => [id, ...current.filter((value) => value !== id)].slice(0, 8));
    window.setTimeout(() => document.getElementById('storefront')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60);
  }

  function addProduct(product: Product) {
    if (cart.length && cart[0].product.merchant !== product.merchant) {
      setError(t.otherStore);
      return;
    }
    setError('');
    setNotice(`${product.name} · ${t.added}`);
    setCart((current) => {
      const found = current.find((line) => line.product.id === product.id);
      if (found) {
        return current.map((line) =>
          line.product.id === product.id ? { ...line, quantity: Math.min(50, line.quantity + 1) } : line
        );
      }
      return [...current, { product, quantity: 1 }];
    });
  }

  function changeQuantity(id: number, delta: number) {
    setCart((current) =>
      current
        .map((line) => (line.product.id === id ? { ...line, quantity: line.quantity + delta } : line))
        .filter((line) => line.quantity > 0 && line.quantity <= 50)
    );
  }

  function locate() {
    if (!navigator.geolocation) {
      setError(t.selectLocation);
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setCoords({ lat: position.coords.latitude, lng: position.coords.longitude });
        setLocating(false);
        setError('');
      },
      () => {
        setLocating(false);
        setError(t.selectLocation);
      },
      { enableHighAccuracy: true, timeout: 12000 }
    );
  }

  async function checkout(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!cart.length || !address.trim() || dropoffLat == null || dropoffLng == null || submitting) return;
    setSubmitting(true);
    setError('');
    setNotice('');
    const key = globalThis.crypto?.randomUUID?.() || `waselni-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    try {
      const result = await api('/orders/', {
        method: 'POST',
        headers: { 'Idempotency-Key': key },
        body: JSON.stringify({
          merchant: cart[0].product.merchant,
          items: cart.map((line) => ({ product_id: line.product.id, quantity: line.quantity })),
          dropoff_address: address.trim(),
          dropoff_latitude: dropoffLat,
          dropoff_longitude: dropoffLng,
          delivery_fee: deliveryFee,
          dropoff_notes: notes.trim(),
          payment_method: 'cash',
          order_type: 'store',
        }),
      });
      setCart([]);
      setAddress('');
      setDropoffLat(null);
      setDropoffLng(null);
      setNotes('');
      setNotice(`${t.success} #${result.id}`);
      const latest = await api('/orders/');
      setOrders(rows<Order>(latest).slice(0, 4));
    } catch (e) {
      setError(e instanceof Error ? e.message : t.orderError);
    } finally {
      setSubmitting(false);
    }
  }

  const renderRow = (title: string, description: string, items: Merchant[], distances?: Map<number, number>) => {
    if (!items.length) return null;
    return (
      <section className="ds-section">
        <div className="ds-section-head">
          <div>
            <span className="ds-eyebrow">{t.stores}</span>
            <h2>{title}</h2>
            {description && <p>{description}</p>}
          </div>
        </div>
        <div className="cs-store-grid">
          {items.map((merchant) => (
            <StoreCard
              key={merchant.id}
              merchant={merchant}
              selected={selectedMerchant === merchant.id}
              distance={distances?.get(merchant.id) ?? null}
              t={t}
              onSelect={() => selectMerchant(merchant.id)}
            />
          ))}
        </div>
      </section>
    );
  };

  return (
    <div className="cs-shell" dir={rtl ? 'rtl' : 'ltr'}>
      <section className="cs-hero">
        <div className="cs-hero-copy">
          <span className="cs-hero-kicker">WASELNI · PALESTINE</span>
          <h1>{t.greeting}</h1>
          <p>{t.subtitle}</p>
          <div className="cs-hero-search">
            <Icon name="search" size={19} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t.searchPlaceholder}
              aria-label={t.searchPlaceholder}
            />
          </div>
        </div>
        <div className="cs-hero-stats">
          <span className="cs-hero-stat"><Icon name="store" size={13} />{merchants.length} {t.storesCount}</span>
          <span className="cs-hero-stat"><Icon name="check" size={13} />{openCount} {t.openStores}</span>
          <span className="cs-hero-stat"><Icon name="shield" size={13} />{t.cash}</span>
        </div>
      </section>

      <div className="cs-layout">
        <main className="cs-main">
          {categories.length > 1 && (
            <div className="cs-categories" role="group" aria-label={t.allCategories}>
              <button className="ds-chip" aria-pressed={category === 'all'} onClick={() => setCategory('all')}>
                <Icon name="grid" size={13} />{t.allCategories}
              </button>
              {categories.map(([name, count]) => (
                <button
                  key={name}
                  className="ds-chip"
                  aria-pressed={category === name}
                  onClick={() => setCategory(name)}
                >
                  <Icon name="tag" size={13} />{name} <small style={{ opacity: 0.7 }}>{count}</small>
                </button>
              ))}
            </div>
          )}

          {loadingStores ? (
            <div className="ds-section">
              <SkeletonLines count={2} />
              <div style={{ marginTop: '14px' }}><SkeletonCards count={4} /></div>
            </div>
          ) : (
            <>
              {recentMerchants.length > 0 && renderRow(t.recentlyViewed, '', recentMerchants)}
              {featured.length > 0 && renderRow(t.featured, t.deliveryInfo, featured)}
              {topRated.length > 0 && renderRow(t.topRated, t.storeHint, topRated)}

              <section className="ds-section">
                <div className="ds-section-head">
                  <div>
                    <span className="ds-eyebrow">{t.nearby}</span>
                    <h2>{t.nearby}</h2>
                    <p>{coords ? t.deliveryInfo : t.nearbyHint}</p>
                  </div>
                  <button type="button" className="ds-btn ds-btn--ghost ds-btn--sm" onClick={locate} disabled={locating}>
                    <Icon name="navigation" size={14} />{locating ? t.loading : t.locateMe}
                  </button>
                </div>
                {coords && nearby.length > 0 ? (
                  <div className="cs-store-grid">
                    {nearby.map(({ merchant, distance }) => (
                      <StoreCard
                        key={merchant.id}
                        merchant={merchant}
                        selected={selectedMerchant === merchant.id}
                        distance={distance}
                        t={t}
                        onSelect={() => selectMerchant(merchant.id)}
                      />
                    ))}
                  </div>
                ) : (
                  <EmptyState icon="navigation" title={t.nearby} description={t.nearbyHint} />
                )}
              </section>

              <section className="ds-section">
                <div className="ds-section-head">
                  <div>
                    <span className="ds-eyebrow">DISCOVER</span>
                    <h2>{t.stores}</h2>
                    <p>{t.storeHint}</p>
                  </div>
                  <span className="ds-badge">{filteredMerchants.length}</span>
                </div>
                {filteredMerchants.length ? (
                  <div className="cs-store-grid">
                    {filteredMerchants.map((merchant) => (
                      <StoreCard
                        key={merchant.id}
                        merchant={merchant}
                        selected={selectedMerchant === merchant.id}
                        t={t}
                        onSelect={() => selectMerchant(merchant.id)}
                      />
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    icon="search"
                    title={search ? t.searchEmpty : t.noStores}
                    description={search ? t.searchPlaceholder : t.storeHint}
                  />
                )}
              </section>
            </>
          )}

          <section className="ds-section" id="storefront">
            {!activeMerchant ? (
              <EmptyState icon="store" title={t.storeHint} description={t.deliveryInfo} />
            ) : (
              <div className="cs-storefront">
                <div className="cs-storefront-cover">
                  {activeMerchant.cover_image && <img src={mediaUrl(activeMerchant.cover_image)} alt="" loading="lazy" />}
                </div>
                <div className="cs-storefront-head">
                  <span className="cs-storefront-logo">
                    {activeMerchant.image ? <img src={mediaUrl(activeMerchant.image)} alt="" /> : <Icon name="store" size={30} />}
                  </span>
                  <div className="cs-storefront-title">
                    <h2>{activeMerchant.shop_name}</h2>
                    <small>{activeMerchant.description || activeMerchant.category || ''}</small>
                  </div>
                  <div style={{ marginInlineStart: 'auto', display: 'flex', gap: '7px', flexWrap: 'wrap', paddingBottom: '5px' }}>
                    <span className="ds-badge ds-badge--warning"><Icon name="star" size={12} />{ratingOf(activeMerchant).toFixed(1)}</span>
                    <StatusBadge status={activeMerchant.is_open ? 'completed' : 'cancelled'} label={activeMerchant.is_open ? t.open : t.closed} />
                  </div>
                </div>
                <div className="cs-storefront-info">
                  {activeMerchant.address && <span><Icon name="pin" size={14} />{activeMerchant.address}</span>}
                  {activeMerchant.opening_hours && <span><Icon name="clock" size={14} />{activeMerchant.opening_hours}</span>}
                  <span><Icon name="bike" size={14} />{t.deliveryInfo}</span>
                </div>
                <div className="cs-storefront-toolbar">
                  <div className="ds-search">
                    <span className="ds-search-icon"><Icon name="search" size={16} /></span>
                    <input
                      className="ds-input ds-input--search"
                      value={productQuery}
                      onChange={(event) => setProductQuery(event.target.value)}
                      placeholder={t.productSearch}
                      aria-label={t.productSearch}
                    />
                  </div>
                  <div className="ds-seg" role="group" aria-label={t.products}>
                    {([
                      ['recommended', t.sortRecommended],
                      ['price_asc', t.sortPriceAsc],
                      ['price_desc', t.sortPriceDesc],
                    ] as const).map(([value, label]) => (
                      <button key={value} aria-pressed={sort === value} onClick={() => setSort(value)}>{label}</button>
                    ))}
                  </div>
                </div>
                <p style={{ margin: '0 18px 12px', fontSize: '11.5px', color: 'var(--w-muted)' }}>{t.storefrontHint}</p>
                <div className="cs-storefront-products">
                  {loadingProducts ? (
                    <SkeletonCards count={4} />
                  ) : filteredProducts.length ? (
                    filteredProducts.map((product) => (
                      <article className="cs-product" key={product.id}>
                        <div className="cs-product-image">
                          {product.image ? <img src={mediaUrl(product.image)} alt={product.name} loading="lazy" /> : <Icon name="package" size={30} />}
                          {!product.available && <span className="cs-product-unavailable">{t.unavailable}</span>}
                        </div>
                        <div className="cs-product-body">
                          <small style={{ color: 'var(--w-primary)', fontSize: '10.5px', fontWeight: 700 }}>
                            {product.category || activeMerchant.category || ''}
                          </small>
                          <h3>{product.name}</h3>
                          {product.description && <p>{product.description}</p>}
                          <div className="cs-product-foot">
                            <span className="cs-product-price">{money(product.price)}</span>
                            <button
                              type="button"
                              className="ds-btn ds-btn--sm"
                              onClick={() => addProduct(product)}
                              disabled={!activeMerchant.is_open}
                              aria-label={`${t.add} ${product.name}`}
                            >
                              <Icon name="plus" size={14} />{t.add}
                            </button>
                          </div>
                        </div>
                      </article>
                    ))
                  ) : (
                    <EmptyState icon="package" title={t.noProducts} description={productQuery ? t.searchEmpty : t.storefrontHint} />
                  )}
                </div>
              </div>
            )}
          </section>

          <section className="ds-section">
            <div className="ds-section-head">
              <div>
                <span className="ds-eyebrow">ACTIVITY</span>
                <h2>{t.orders}</h2>
              </div>
              <Link className="ds-btn ds-btn--ghost ds-btn--sm" to="/orders">
                <Icon name="map-pin" size={14} />{t.trackOrder}
              </Link>
            </div>
            {orders.length ? (
              <div style={{ display: 'grid', gap: '9px' }}>
                {orders.map((order) => (
                  <div className="ds-card" key={order.id} style={{ padding: '12px 14px', display: 'flex', alignItems: 'center', gap: '11px', flexWrap: 'wrap' }}>
                    <span className="ds-empty-icon" style={{ width: '38px', height: '38px', borderRadius: '12px', marginBottom: 0 }}>
                      <Icon name={order.order_type === 'ride' ? 'bike' : 'package'} size={17} />
                    </span>
                    <div style={{ display: 'grid', gap: '2px', flex: 1, minWidth: '140px' }}>
                      <b style={{ fontSize: '13px' }}>#{order.id} · {order.merchant_name || 'WASELNI'}</b>
                      <small style={{ color: 'var(--w-muted)', fontSize: '11px' }}>{order.dropoff_address || ''}</small>
                    </div>
                    <StatusBadge status={order.status} label={t.statusLabels[order.status] || order.status} />
                    <b style={{ fontSize: '13px' }}>{money(order.total)}</b>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState icon="orders" title={t.orders} description={t.emptyHint} />
            )}
          </section>
        </main>

        <aside className="ds-card cs-cart">
          <div className="ds-section-head" style={{ marginBottom: '8px' }}>
            <div>
              <span className="ds-eyebrow">YOUR ORDER</span>
              <h2 style={{ fontSize: '18px' }}>{t.cart}</h2>
            </div>
            <span className="ds-badge"><Icon name="package" size={12} />{cartCount}</span>
          </div>
          <p style={{ margin: '0 0 12px', fontSize: '11px', color: 'var(--w-muted)' }}>{t.cartHint}</p>

          {cart.length ? (
            <>
              <div className="cs-cart-lines">
                {cart.map((line) => (
                  <div className="cs-cart-line" key={line.product.id}>
                    <span className="cs-cart-thumb">
                      {line.product.image ? <img src={mediaUrl(line.product.image)} alt="" /> : <Icon name="package" size={17} />}
                    </span>
                    <div className="cs-cart-copy">
                      <b>{line.product.name}</b>
                      <small>{money(Number(line.product.price) * line.quantity)}</small>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <div className="cs-qty">
                        <button type="button" onClick={() => changeQuantity(line.product.id, -1)} aria-label={t.remove}>
                          <Icon name="minus" size={13} />
                        </button>
                        <span>{line.quantity}</span>
                        <button type="button" onClick={() => changeQuantity(line.product.id, 1)} aria-label={t.add}>
                          <Icon name="plus" size={13} />
                        </button>
                      </div>
                      <button
                        type="button"
                        className="cs-cart-remove"
                        aria-label={`${t.remove} ${line.product.name}`}
                        onClick={() => setCart((current) => current.filter((item) => item.product.id !== line.product.id))}
                      >
                        <Icon name="trash" size={14} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              <button type="button" className="ds-btn ds-btn--outline ds-btn--sm" onClick={() => setCart([])} style={{ marginTop: '10px' }}>
                <Icon name="x" size={13} />{t.clearCart}
              </button>
            </>
          ) : (
            <EmptyState icon="package" title={t.empty} description={t.emptyHint} />
          )}

          <div className="cs-totals">
            <div className="cs-totals-row"><span>{t.subtotal}</span><b>{money(subtotal)}</b></div>
            <div className="cs-totals-row"><span>{t.deliveryFee}</span><b>{money(deliveryFee)}</b></div>
            <div className="cs-totals-total"><span>{t.total}</span><strong>{money(subtotal + Number(deliveryFee || 0))}</strong></div>
            <small style={{ color: 'var(--w-muted)', fontSize: '10.5px', lineHeight: 1.55 }}>{t.deliveryFeeNote}</small>
          </div>

          <form onSubmit={checkout} style={{ display: 'grid', gap: '11px', marginTop: '14px' }}>
            <label className="ds-field">
              <span>{t.address}</span>
              <input
                className="ds-input"
                required
                value={address}
                onChange={(event) => setAddress(event.target.value)}
                placeholder={t.address}
              />
            </label>
            <label className="ds-field">
              <span>{t.deliveryFee}</span>
              <input
                className="ds-input"
                type="number"
                min="0.50"
                max="500"
                step="0.50"
                required
                value={deliveryFee}
                onChange={(event) => setDeliveryFee(event.target.value)}
              />
            </label>
            <div className="ds-field">
              <span>{t.customerLocation}</span>
              <CheckoutLocationMap
                merchant={activeMerchant}
                latitude={dropoffLat}
                longitude={dropoffLng}
                onSelect={(lat, lng, place) => {
                  setDropoffLat(lat);
                  setDropoffLng(lng);
                  if (place) setAddress(place);
                }}
                t={t}
              />
            </div>
            <label className="ds-field">
              <span>{t.notes}</span>
              <textarea className="ds-input" rows={2} value={notes} onChange={(event) => setNotes(event.target.value)} />
            </label>
            <div className="ds-alert ds-alert--info" style={{ alignItems: 'center' }}>
              <Icon name="wallet" size={16} />
              <span><b>{t.cash}</b></span>
            </div>
            <button
              className="ds-btn ds-btn--block"
              disabled={
                !cart.length || !address.trim() || dropoffLat == null || dropoffLng == null ||
                !activeMerchant || !hasPoint(activeMerchant.latitude, activeMerchant.longitude) || submitting
              }
            >
              {submitting ? t.loading : t.placeOrder}
              <Icon name={rtl ? 'chevronLeft' : 'chevronRight'} size={16} />
            </button>
          </form>

          {error && <p className="ds-alert ds-alert--error" role="alert" style={{ marginTop: '10px' }}>{error}</p>}
          {notice && <p className="ds-alert ds-alert--success" role="status" style={{ marginTop: '10px' }}>{notice}</p>}
        </aside>
      </div>
    </div>
  );
}
