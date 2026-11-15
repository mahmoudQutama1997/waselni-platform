import L from '../map/leaflet';
import { createTileLayer } from '../map/tiles';
import { mapMarker } from '../map/markers';
import { useEffect, useMemo, useState, useRef } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { api, roundCoordinate } from '../api';
import SafeImage from '../components/SafeImage';
import ServiceIcon from '../components/ServiceIcon';
import type { CartLine, Merchant, Order, Product } from './types';
import { GEOCODING_REVERSE_URL, GEOCODING_SEARCH_URL, geocodeUrl } from '../config';

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
  cart: string;
  empty: string;
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
  clearCart: string;
  deliveryFeeNote: string;
  deliveryFee: string;
  storeLocation: string;
  customerLocation: string;
  selectLocation: string;
  useLocation: string;
  browseCategories: string;
  services: string;
  storeService: string;
  storeServiceHint: string;
  rideService: string;
  rideServiceHint: string;
  viewCart: string;
  orderStatus: string;
  confirmReceipt: string;
  paymentStatus: string;
  cashStatus: string;
  onlineNotIntegrated: string;
  noOrders: string;
  closedHint: string;
  results: string;
  searchAddress: string;
  searchAction: string;
  searching: string;
  addressNotFound: string;
  locationDenied: string;
  locationUnsupported: string;
  outOfStock: string;
  lowStock: string;
  stockLeft: string;
  itemSoldOut: string;
  cartStockAlert: string;
  cartStockClamped: string;
  maxReached: string;
  stockShortfall: string;
  stockUntracked: string;
};

const copy: Record<Props['lang'], Copy> = {
  ar: {
    greeting: 'كل احتياجاتك، توصلك',
    subtitle: 'تسوّق من متاجرك المفضلة في فلسطين بكل سهولة.',
    search: 'ابحث عن متجر أو منتج...',
    stores: 'المتاجر القريبة',
    all: 'الكل',
    products: 'المنتجات',
    add: 'أضف للسلة',
    added: 'أضيفت للسلة',
    cart: 'سلة المشتريات',
    empty: 'سلتك فارغة حالياً',
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
    searchEmpty: 'لا توجد نتائج مطابقة.',
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
    clearCart: 'إفراغ السلة',
    deliveryFeeNote: 'حدد أجرة التوصيل التي تعرض على الكابتن؛ لا تُثبت إلا بعد موافقته.', deliveryFee: 'أجرة التوصيل المقترحة (₪)', storeLocation: 'موقع المتجر', customerLocation: 'حدد موقع استلام الطلب على الخريطة', selectLocation: 'اضغط على الخريطة لتحديد موقعك أو ابحث عن عنوانك.', useLocation: 'استخدم موقعي الحالي',
    browseCategories: 'تصفح التصنيفات',
    services: 'خدمات وصلني',
    storeService: 'توصيل المتاجر',
    storeServiceHint: 'اطلب من متاجرك المفضلة',
    rideService: 'ركوب الفسبا',
    rideServiceHint: 'تنقل سريع داخل المدينة',
    viewCart: 'عرض السلة',
    orderStatus: 'حالة الطلب',
    confirmReceipt: 'تأكيد استلام الطلب',
    paymentStatus: 'حالة الدفع',
    cashStatus: 'الدفع نقداً للكابتن عند التسليم',
    onlineNotIntegrated: 'الدفع الإلكتروني غير مفعّل؛ لم يتم تأكيد الدفع',
    noOrders: 'لا توجد طلبات سابقة بعد.',
    closedHint: 'هذا المتجر مغلق حالياً، يمكنك التصفح لكن الطلب قد يتأخر.',
    results: 'نتيجة',
    searchAddress: 'ابحث عن المدينة أو الشارع',
    searchAction: 'بحث',
    searching: 'جارٍ البحث...',
    addressNotFound: 'لم يتم العثور على العنوان',
    locationDenied: 'اسمح بالوصول إلى الموقع من المتصفح',
    locationUnsupported: 'المتصفح لا يدعم تحديد الموقع',
    outOfStock: 'نفدت الكمية',
    lowStock: 'كمية محدودة',
    stockLeft: 'المتوفر',
    itemSoldOut: 'نفدت الكمية من هذا المنتج.',
    cartStockAlert: 'نفدت الكمية من بعض منتجات سلتك وتم حذفها:',
    cartStockClamped: 'تم تعديل الكميات حسب المتوفر في المتجر:',
    maxReached: 'وصلت للحد الأقصى المتوفر من هذا المنتج.',
    stockShortfall: 'الكمية غير كافية: {name} — المتوفر {count} فقط.',
    stockUntracked: '{name} غير متاح للطلب حتى يحدد المتجر كميته.'
  },

  en: {
    greeting: 'Everything you need, delivered',
    subtitle: 'Shop your favourite local stores across Palestine.',
    search: 'Search stores or products...',
    stores: 'Available stores',
    all: 'All',
    products: 'Products',
    add: 'Add to cart',
    added: 'Added to cart',
    cart: 'Your cart',
    empty: 'Your cart is empty',
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
    searchEmpty: 'No matching results.',
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
    clearCart: 'Clear cart',
    deliveryFeeNote: 'Set your proposed delivery fee. It becomes final only after a captain accepts it.', deliveryFee: 'Proposed delivery fee (₪)', storeLocation: 'Store location', customerLocation: 'Choose your delivery location on the map', selectLocation: 'Click the map to set your location or search for an address.', useLocation: 'Use my current location',
    browseCategories: 'Browse categories',
    services: 'Waselni services',
    storeService: 'Store delivery',
    storeServiceHint: 'Order from your favourite stores',
    rideService: 'Scooter ride',
    rideServiceHint: 'Quick rides around the city',
    viewCart: 'View cart',
    orderStatus: 'Order status',
    confirmReceipt: 'Confirm order receipt',
    paymentStatus: 'Payment status',
    cashStatus: 'Cash payable to the captain on delivery',
    onlineNotIntegrated: 'Online payment is not enabled; payment has not been verified',
    noOrders: 'No previous orders yet.',
    closedHint: 'This store is currently closed. You can browse, but the order may be delayed.',
    results: 'results',
    searchAddress: 'Search for a city or street',
    searchAction: 'Search',
    searching: 'Searching...',
    addressNotFound: 'Address not found',
    locationDenied: 'Allow location access from your browser',
    locationUnsupported: 'Geolocation is not supported by this browser',
    outOfStock: 'Out of stock',
    lowStock: 'Low stock',
    stockLeft: 'Available',
    itemSoldOut: 'This item is out of stock.',
    cartStockAlert: 'Some items sold out and were removed from your cart:',
    cartStockClamped: 'Quantities were adjusted to the available stock:',
    maxReached: 'You reached the maximum available quantity for this item.',
    stockShortfall: 'Not enough stock: {name} — only {count} left.',
    stockUntracked: '{name} cannot be ordered until the store sets its quantity.'
  },

  he: {
    greeting: 'כל מה שצריך, עד אליך',
    subtitle: 'קונים בקלות מהחנויות המקומיות האהובות עליכם.',
    search: 'חיפוש חנות או מוצר...',
    stores: 'חנויות זמינות',
    all: 'הכל',
    products: 'מוצרים',
    add: 'הוספה לסל',
    added: 'נוסף לסל',
    cart: 'סל הקניות',
    empty: 'סל הקניות ריק',
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
    searchEmpty: 'לא נמצאו תוצאות.',
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
    clearCart: 'ריקון הסל',
    deliveryFeeNote: 'קבעו דמי משלוח מוצעים. המחיר יאושר סופית רק לאחר שקברניט יקבל אותו.', deliveryFee: 'דמי משלוח מוצעים (₪)', storeLocation: 'מיקום החנות', customerLocation: 'בחרו את מיקום המסירה במפה', selectLocation: 'לחצו על המפה כדי לבחור מיקום או חפשו כתובת.', useLocation: 'השתמשו במיקום שלי',
    browseCategories: 'עיון בקטגוריות',
    services: 'שירותי وصلني',
    storeService: 'משלוח מחנויות',
    storeServiceHint: 'הזמינו מהחנויות האהובות עליכם',
    rideService: 'נסיעת קטנוע',
    rideServiceHint: 'נסיעות מהירות בעיר',
    viewCart: 'לצפייה בסל',
    orderStatus: 'מצב הזמנה',
    confirmReceipt: 'אישור קבלת ההזמנה',
    paymentStatus: 'מצב התשלום',
    cashStatus: 'תשלום במזומן לשליח בעת המסירה',
    onlineNotIntegrated: 'תשלום מקוון אינו פעיל; התשלום לא אומת',
    noOrders: 'אין עדיין הזמנות קודמות.',
    closedHint: 'החנות סגורה כעת. אפשר לעיין, אך ייתכן עיכוב בהזמנה.',
    results: 'תוצאות',
    searchAddress: 'חיפוש עיר או רחוב',
    searchAction: 'חיפוש',
    searching: 'מחפש...',
    addressNotFound: 'הכתובת לא נמצאה',
    locationDenied: 'יש לאשר גישה למיקום בדפדפן',
    locationUnsupported: 'הדפדפן אינו תומך באיתור מיקום',
    outOfStock: 'אזל מהמלאי',
    lowStock: 'מלאי מוגבל',
    stockLeft: 'זמין',
    itemSoldOut: 'הפריט אזל מהמלאי.',
    cartStockAlert: 'חלק מהפריטים אזלו והוסרו מהסל:',
    cartStockClamped: 'הכמויות עודכנו לפי המלאי הזמין:',
    maxReached: 'הגעתם לכמות המרבית הזמינה של פריט זה.',
    stockShortfall: 'אין מספיק מלאי: {name} — נותרו {count} בלבד.',
    stockUntracked: 'לא ניתן להזמין את {name} עד שהחנות תגדיר כמות.'
  }
};

const ORDER_STATUS: Record<Props['lang'], Record<string, string>> = {
  ar: { new: 'جديد', accepted: 'مقبول', preparing: 'قيد التجهيز', ready: 'جاهز', assigned: 'تم تعيين كابتن', picked_up: 'تم الاستلام', delivering: 'قيد التوصيل', awaiting_confirmation: 'بانتظار تأكيد الزبون', completed: 'مكتمل', cancelled: 'ملغي' },
  en: { new: 'New', accepted: 'Accepted', preparing: 'Preparing', ready: 'Ready', assigned: 'Captain assigned', picked_up: 'Picked up', delivering: 'Delivering', awaiting_confirmation: 'Awaiting customer confirmation', completed: 'Completed', cancelled: 'Cancelled' },
  he: { new: 'חדש', accepted: 'אושר', preparing: 'בהכנה', ready: 'מוכן', assigned: 'שליח שובץ', picked_up: 'נאסף', delivering: 'במשלוח', awaiting_confirmation: 'ממתין לאישור הלקוח', completed: 'הושלם', cancelled: 'בוטל' }
};

const money = (value: string | number) =>
  `${Number(value || 0).toFixed(2)} ₪`;

const statusTone = (status: string) =>
  status === 'cancelled'
    ? 'is-cancelled'
    : status === 'completed'
      ? 'is-done'
      : status === 'new'
        ? 'is-new'
        : 'is-live';

type StockState = 'untracked' | 'out' | 'low' | 'in';

const stockState = (product: Product): StockState =>
  product.stock_status ||
  (typeof product.quantity === 'number'
    ? product.quantity <= 0
      ? 'out'
      : product.quantity <= (product.low_stock_threshold ?? 5)
        ? 'low'
        : 'in'
    : 'untracked');

const stockLimit = (product: Product): number | null =>
  typeof product.quantity === 'number' ? Math.max(0, product.quantity) : 0;

// An unset count is not "unlimited": the backend refuses to sell it, so the
// storefront must show it as unavailable instead of letting the customer add it.
const isSoldOut = (product: Product) =>
  product.available === false ||
  stockState(product) === 'out' ||
  stockState(product) === 'untracked';

type StockShortfall = {
  product_id: number;
  name: string;
  available: number;
  requested: number;
  reason?: 'shortage' | 'untracked';
};

const stockErrorMessage = (
  payload: unknown,
  t: Copy
): string | null => {
  const stock = (payload as { stock?: StockShortfall[] } | null)?.stock;
  if (!Array.isArray(stock) || !stock.length) return null;
  return stock
    .map(row =>
      (row.reason === 'untracked' ? t.stockUntracked : t.stockShortfall)
        .replace('{name}', row.name)
        .replace('{count}', String(row.available))
    )
    .join(' — ');
};


const readCart = (): CartLine[] => {
  try {
    return JSON.parse(
      localStorage.getItem('waselni_customer_cart') || '[]'
    ) as CartLine[];
  } catch {
    return [];
  }
};

const rows = <T,>(value: unknown): T[] =>
  Array.isArray(value)
    ? value as T[]
    : ((value as { results?: T[] })?.results || []);

function CheckoutLocationMap({ merchant, latitude, longitude, onSelect, t }: { merchant: Merchant | null; latitude: number | null; longitude: number | null; onSelect: (lat: number, lng: number, address?: string) => void; t: Copy }) {
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
    createTileLayer({ maxZoom: 19 }).addTo(map);
    map.on('click', (event: any) => select(event.latlng.lat, event.latlng.lng));
    mapInstance.current = map;
    const timer = window.setTimeout(() => map.invalidateSize(), 180);
    return () => { window.clearTimeout(timer); map.remove(); mapInstance.current = null; customerMarker.current = null; storeMarker.current = null; };
  }, []);
  useEffect(() => {
    const map = mapInstance.current;
if (!map) return;
    if (!L || !map) return;
    if (merchant?.latitude != null && merchant?.longitude != null) {
      const point = [Number(merchant.latitude), Number(merchant.longitude)];
      if (point.every(Number.isFinite)) {
        if (storeMarker.current) storeMarker.current.setLatLng(point);
        else storeMarker.current = L.circleMarker(point, { radius: 10, color: '#fff', weight: 3, fillColor: '#6b35a6', fillOpacity: 1 }).addTo(map).bindPopup(merchant.shop_name);
      }
    } else if (storeMarker.current) { map.removeLayer(storeMarker.current); storeMarker.current = null; }
    if (latitude != null && longitude != null) {
      const point = [latitude, longitude];
      if (customerMarker.current) customerMarker.current.setLatLng(point);
      else customerMarker.current = L.marker(point, { draggable: true, icon: mapMarker('customer') }).addTo(map).bindPopup(t.customerLocation);
      customerMarker.current.off('dragend').on('dragend', (event: any) => { const p = event.target.getLatLng(); select(p.lat, p.lng); });
    } else if (customerMarker.current) { map.removeLayer(customerMarker.current); customerMarker.current = null; }
    const points: number[][] = [];
    if (merchant?.latitude != null && merchant?.longitude != null) points.push([Number(merchant.latitude), Number(merchant.longitude)]);
    if (latitude != null && longitude != null) points.push([latitude, longitude]);
    if (points.length > 1) map.fitBounds(points, { padding: [35, 35], maxZoom: 15 });
    else if (points.length) map.setView(points[0], 15);
  }, [merchant?.latitude, merchant?.longitude, merchant?.shop_name, latitude, longitude, t.customerLocation]);
  async function select(lat: number, lng: number) {
    onSelect(lat, lng);
    try {
      const response = await fetch(geocodeUrl(GEOCODING_REVERSE_URL, { format: 'jsonv2', lat, lon: lng, 'accept-language': document.documentElement.lang || 'ar' }));
      if (response.ok) { const data = await response.json(); if (data.display_name) onSelect(lat, lng, data.display_name); }
    } catch { /* Coordinates remain usable if reverse geocoding is unavailable. */ }
  }
  async function search(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault(); if (!query.trim() || searching) return;
    setSearching(true);
    try {
      setMapError('');
      const response = await fetch(geocodeUrl(GEOCODING_SEARCH_URL, { format: 'jsonv2', limit: 1, q: query }));
      if (!response.ok) throw new Error(t.addressNotFound);
      const results = await response.json(); if (!results.length) throw new Error(t.addressNotFound);
      const lat = Number(results[0].lat), lng = Number(results[0].lon);
      onSelect(lat, lng, results[0].display_name || query); mapInstance.current?.setView([lat, lng], 16);
    } catch (error) { setMapError(error instanceof Error ? error.message : t.addressNotFound); }
    finally { setSearching(false); }
  }
  function locate() {
    if (!navigator.geolocation) { setMapError(t.locationUnsupported); return; }
    navigator.geolocation.getCurrentPosition(position => { const { latitude: lat, longitude: lng } = position.coords; select(lat, lng); mapInstance.current?.setView([lat, lng], 16); setMapError(''); }, () => setMapError(t.locationDenied), { enableHighAccuracy: true, timeout: 12000 });
  }
  return <div className="checkout-location-wrap"><div className="checkout-location-tools"><input value={query} onChange={event => setQuery(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); search(); } }} placeholder={t.searchAddress}/><button type="button" disabled={searching} onClick={() => search()}>{searching ? t.searching : t.searchAction}</button><button type="button" className="secondary" onClick={locate}>{t.useLocation}</button></div><div ref={mapRef} className="checkout-location-map"/><p className="muted-note">{t.selectLocation} {merchant ? `${t.storeLocation}: ${merchant.shop_name}` : ''}</p><div className="checkout-map-legend"><span><i className="checkout-store-dot"/> {t.storeLocation}</span><span><i className="checkout-customer-dot"/> {t.customerLocation}</span></div>{latitude != null && longitude != null && <small dir="ltr">{latitude.toFixed(6)}, {longitude.toFixed(6)}</small>}{mapError && <p className="error">{mapError}</p>}</div>;
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
  const [category, setCategory] = useState('');
  const [addedId, setAddedId] = useState<number | null>(null);
  const cartPanelRef = useRef<HTMLElement | null>(null);
  const [address, setAddress] = useState('');
  const [notes, setNotes] = useState('');
  const [dropoffLat, setDropoffLat] = useState<number | null>(null);
  const [dropoffLng, setDropoffLng] = useState<number | null>(null);
  const [deliveryFee, setDeliveryFee] = useState('10.00');
  const [loadingStores, setLoadingStores] = useState(true);
  const [loadingProducts, setLoadingProducts] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [confirmingOrderId, setConfirmingOrderId] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    let alive = true;

    api('/merchants/')
      .then(data => {
        if (alive) setMerchants(rows<Merchant>(data));
      })
      .catch(e => {
        if (alive) setError(e.message || t.orderError);
      })
      .finally(() => {
        if (alive) setLoadingStores(false);
      });

    const loadOrders = () => api('/orders/')
      .then(data => {
        if (alive) setOrders(rows<Order>(data).slice(0, 3));
      })
      .catch(() => undefined);
    loadOrders();
    const orderTimer = setInterval(loadOrders, 5000);

    return () => {
      alive = false;
      clearInterval(orderTimer);
    };
  }, [t.orderError]);

  async function confirmOrderReceipt(orderId: number) {
    if (confirmingOrderId) return;
    setConfirmingOrderId(orderId);
    try {
      await api(`/orders/${orderId}/status/`, {
        method: 'POST',
        body: JSON.stringify({ status: 'completed' })
      });
      setOrders(rows<Order>(await api('/orders/')).slice(0, 3));
    } catch (e) {
      setError(e instanceof Error ? e.message : t.orderError);
    } finally {
      setConfirmingOrderId(null);
    }
  }

  useEffect(() => {
    localStorage.setItem('waselni_customer_cart', JSON.stringify(cart));
  }, [cart]);

  useEffect(() => {
    if (cart.length && !selectedMerchant) setSelectedMerchant(cart[0].product.merchant);
  }, []);

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
      .then(data => {
        if (alive) {
          setProducts(
            rows<Product>(data).filter(p => p.available !== false)
          );
        }
      })
      .catch(e => {
        if (alive) setError(e.message || t.orderError);
      })
      .finally(() => {
        if (alive) setLoadingProducts(false);
      });

    return () => {
      alive = false;
    };
  }, [selectedMerchant, t.orderError]);

  const activeMerchant =
    merchants.find(m => m.id === selectedMerchant) || null;

  const filteredMerchants = useMemo(
    () =>
      merchants.filter(m => {
        const matchesSearch = `${m.shop_name} ${m.category || ''}`
          .toLowerCase()
          .includes(search.toLowerCase());
        const matchesCategory = !category || m.category === category;
        return matchesSearch && matchesCategory;
      }),
    [merchants, search, category]
  );

  const categories = useMemo(() => {
    const counts = new Map<string, number>();
    merchants.forEach(m => {
      const label = (m.category || '').trim();
      if (label) counts.set(label, (counts.get(label) || 0) + 1);
    });
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8);
  }, [merchants]);

  const filteredProducts = useMemo(
    () =>
      products.filter(p =>
        `${p.name} ${p.category || ''}`
          .toLowerCase()
          .includes(search.toLowerCase())
      ),
    [products, search]
  );

  const subtotal = cart.reduce(
    (sum, line) =>
      sum + Number(line.product.price) * line.quantity,
    0
  );

  const cartCount = cart.reduce(
    (sum, line) => sum + line.quantity,
    0
  );

  const cartInvalid = cart.some(line => {
    const limit = stockLimit(line.product);
    return isSoldOut(line.product) || (limit != null && line.quantity > limit);
  });

  const cartRef = useRef(cart);
  useEffect(() => {
    cartRef.current = cart;
  }, [cart]);

  async function revalidateCart(announce: boolean) {
    const current = cartRef.current;
    const merchantId = current[0]?.product.merchant;
    if (!merchantId) return true;

    try {
      const data = await api(`/products/?merchant=${merchantId}`);
      const fresh = rows<Product>(data);
      const byId = new Map(fresh.map(product => [product.id, product]));
      const removed: string[] = [];
      const clamped: string[] = [];
      const next: CartLine[] = [];

      current.forEach(line => {
        const product = byId.get(line.product.id);
        const limit = product ? stockLimit(product) : 0;

        if (!product || isSoldOut(product) || limit === 0) {
          removed.push(line.product.name);
          return;
        }

        if (limit != null && line.quantity > limit) {
          clamped.push(`${line.product.name} (${limit})`);
          next.push({ product, quantity: limit });
          return;
        }

        next.push({ product, quantity: line.quantity });
      });

      if (removed.length || clamped.length) {
        setCart(next);
        if (announce) {
          setNotice('');
          setError(
            [
              removed.length ? `${t.cartStockAlert} ${removed.join('، ')}` : '',
              clamped.length ? `${t.cartStockClamped} ${clamped.join('، ')}` : ''
            ]
              .filter(Boolean)
              .join(' — ')
          );
        }
        return false;
      }

      setProducts(fresh.filter(product => product.available !== false));
      return true;
    } catch {
      return true;
    }
  }

  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState !== 'visible') return;
      // Tell the customer when returning to the tab removes or shrinks a cart
      // line; unchanged carts announce nothing, so the alert never repeats.
      void revalidateCart(true);
    };
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [t]);

  function addProduct(product: Product) {
    if (
      cart.length &&
      cart[0].product.merchant !== product.merchant
    ) {
      setError(t.chooseStore);
      return;
    }

    if (isSoldOut(product)) {
      setNotice('');
      setError(`${product.name}: ${t.itemSoldOut}`);
      return;
    }

    const limit = stockLimit(product);
    const inCart =
      cart.find(line => line.product.id === product.id)?.quantity || 0;

    if (limit != null && inCart >= limit) {
      setNotice('');
      setError(`${product.name}: ${t.maxReached}`);
      return;
    }

    setError('');
    setNotice(t.added);
    setAddedId(product.id);
    window.setTimeout(() => setAddedId(current => (current === product.id ? null : current)), 1400);

    setCart(current => {
      const found = current.find(
        line => line.product.id === product.id
      );

      if (found) {
        const cap = limit == null ? 50 : Math.min(50, limit);
        return current.map(line =>
          line.product.id === product.id
            ? {
                ...line,
                product,
                quantity: Math.min(cap, line.quantity + 1)
              }
            : line
        );
      }

      return [...current, { product, quantity: 1 }];
    });
  }

  function changeQuantity(id: number, delta: number) {
    const line = cart.find(item => item.product.id === id);
    if (!line) return;

    const limit = stockLimit(line.product);

    if (delta > 0 && limit != null && line.quantity >= limit) {
      setError(t.maxReached);
      return;
    }

    setError('');

    setCart(current =>
      current
        .map(item => {
          if (item.product.id !== id) return item;
          const max = limit == null ? 50 : Math.min(50, limit);
          return {
            ...item,
            quantity: Math.max(0, Math.min(max, item.quantity + delta))
          };
        })
        .filter(item => item.quantity > 0)
    );
  }

  async function checkout(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!cart.length || !address.trim() || dropoffLat == null || dropoffLng == null || submitting) return;

    setSubmitting(true);
    setError('');
    setNotice('');

    const fresh = await revalidateCart(true);
    if (!fresh) {
      setSubmitting(false);
      return;
    }

    const key =
      globalThis.crypto?.randomUUID?.() ||
      `waselni-${Date.now()}-${Math.random().toString(36).slice(2)}`;

    const merchantId = cart[0].product.merchant;

    try {
      const result = await api('/orders/', {
        method: 'POST',
        headers: { 'Idempotency-Key': key },
        body: JSON.stringify({
          merchant: merchantId,
          items: cart.map(line => ({
            product_id: line.product.id,
            quantity: line.quantity
          })),
          dropoff_address: address.trim(),
          dropoff_latitude: roundCoordinate(dropoffLat),
          dropoff_longitude: roundCoordinate(dropoffLng),
          delivery_fee: deliveryFee,
          dropoff_notes: notes.trim(),
          payment_method: 'cash',
          order_type: 'store'
        })
      });

      setCart([]);
      setAddress('');
      setDropoffLat(null);
      setDropoffLng(null);
      setNotes('');
      setNotice(`${t.success} #${result.id}`);

      const latest = await api('/orders/');
      setOrders(rows<Order>(latest).slice(0, 3));
      // The order just consumed stock; refresh the shelf so the remaining
      // count drops immediately instead of waiting for the next focus event.
      void api(`/products/?merchant=${merchantId}`)
        .then(data => setProducts(rows<Product>(data).filter(product => product.available !== false)))
        .catch(() => undefined);
    } catch (e) {
      const stockMessage = stockErrorMessage(
        e instanceof Error ? (e as Error & { data?: unknown }).data : null,
        t
      );
      setError(stockMessage || (e instanceof Error ? e.message : t.orderError));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="customer-v2" dir={rtl ? 'rtl' : 'ltr'}>
      <section className="customer-v2-hero">
        <div className="customer-v2-hero-copy">
          <span className="customer-v2-kicker">
            WASELNI · PALESTINE
          </span>
          <h1>{t.greeting}</h1>
          <p>{t.subtitle}</p>

          <div className="customer-v2-search">
            <span aria-hidden="true">⌕</span>
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder={t.search}
              aria-label={t.search}
            />
          </div>

          <nav className="customer-v2-services" aria-label={t.services}>
            <a
              className="customer-v2-service customer-v2-service--store"
              href="#stores"
            >
              <ServiceIcon name="store" size="lg" />
              <span>
                <b>{t.storeService}</b>
                <small>{t.storeServiceHint}</small>
              </span>
            </a>
            <Link
              className="customer-v2-service customer-v2-service--ride"
              to="/ride"
            >
              <ServiceIcon name="vespa" size="lg" />
              <span>
                <b>{t.rideService}</b>
                <small>{t.rideServiceHint}</small>
              </span>
            </Link>
          </nav>
        </div>

        <div className="customer-v2-hero-art" aria-hidden="true">
          <span className="hero-orbit orbit-one" />
          <span className="hero-orbit orbit-two" />
          <span className="hero-bag">و</span>
          <span className="hero-spark">✦</span>
        </div>
      </section>

      <div className="customer-v2-layout">
        <main className="customer-v2-main">
          <section className="customer-v2-section" id="stores">
            <div className="customer-v2-heading">
              <div>
                <span className="customer-v2-eyebrow">DISCOVER</span>
                <h2>{t.stores}</h2>
                <p>{t.storeHint}</p>
              </div>
              <span className="customer-v2-count">
                {filteredMerchants.length}
              </span>
            </div>

            {categories.length > 0 && (
              <div className="customer-v2-categories" aria-label={t.browseCategories}>
                <button
                  type="button"
                  className={`customer-v2-category ${!category ? 'is-active' : ''}`}
                  onClick={() => setCategory('')}
                  aria-pressed={!category}
                >
                  {t.all} <b>{merchants.length}</b>
                </button>
                {categories.map(([label, count]) => (
                  <button
                    type="button"
                    key={label}
                    className={`customer-v2-category ${category === label ? 'is-active' : ''}`}
                    onClick={() => setCategory(current => (current === label ? '' : label))}
                    aria-pressed={category === label}
                  >
                    {label} <b>{count}</b>
                  </button>
                ))}
              </div>
            )}

            {loadingStores ? (
              <div className="customer-v2-stores" aria-busy="true" aria-label={t.loading}>
                {[0, 1, 2, 3].map(i => (
                  <div className="customer-v2-skeleton-store" key={i}>
                    <span className="skeleton sk-avatar" />
                    <span className="sk-block">
                      <span className="skeleton sk-line w-80" />
                      <span className="skeleton sk-line w-40" />
                    </span>
                  </div>
                ))}
              </div>
            ) : filteredMerchants.length ? (
              <div className="customer-v2-stores">
                {filteredMerchants.map(merchant => (
                  <button
                    key={merchant.id}
                    className={`customer-v2-store ${
                      selectedMerchant === merchant.id
                        ? 'is-selected'
                        : ''
                    }`}
                    onClick={() => {
                      setSelectedMerchant(merchant.id);
                      setError('');
                    }}
                    aria-pressed={selectedMerchant === merchant.id}
                  >
                    <span className="customer-v2-store-image">
                      {merchant.image ? (
                        <SafeImage src={merchant.image} alt={merchant.shop_name} />
                      ) : (
                        <span>◈</span>
                      )}
                    </span>

                    <span className="customer-v2-store-info">
                      <b>{merchant.shop_name}</b>
                      <small>{merchant.category || t.category}</small>
                      <em className={merchant.is_open ? 'is-open' : 'is-closed'}>
                        {merchant.is_open ? t.open : t.closed}
                      </em>
                    </span>

                    <span className="customer-v2-chevron">‹</span>
                  </button>
                ))}
              </div>
            ) : (
              <p className="customer-v2-empty">
                {search || category ? t.searchEmpty : t.noStores}
              </p>
            )}
            {activeMerchant && <div className="customer-v2-store-location"><b>{t.storeLocation}: {activeMerchant.shop_name}</b><small>{activeMerchant.address || '—'}</small>{activeMerchant.latitude == null || activeMerchant.longitude == null ? <p className="customer-v2-fee-note">{lang === 'ar' ? 'المتجر لم يحدد موقعه على الخريطة بعد؛ لا يمكن إرسال طلب توصيل إليه.' : lang === 'he' ? 'החנות טרם סימנה את מיקומה במפה; לא ניתן לשלוח אליה הזמנת משלוח.' : 'The store has not set its map location yet, so delivery orders cannot be sent to it.'}</p> : <a target="_blank" rel="noreferrer" href={`https://www.openstreetmap.org/?mlat=${activeMerchant.latitude}&mlon=${activeMerchant.longitude}#map=16/${activeMerchant.latitude}/${activeMerchant.longitude}`}>{lang === 'ar' ? 'عرض موقع المتجر على الخريطة' : lang === 'he' ? 'הצגת מיקום החנות במפה' : 'View store location on the map'}</a>}</div>}
            {activeMerchant && !activeMerchant.is_open && <p className="customer-v2-feedback is-error">{t.closedHint}</p>}
          </section>

          <section className="customer-v2-section">
            <div className="customer-v2-heading">
              <div>
                <span className="customer-v2-eyebrow">MENU</span>
                <h2>{activeMerchant?.shop_name || t.products}</h2>
                <p>{t.products}</p>
              </div>
            </div>

            {!selectedMerchant ? (
              <div className="customer-v2-placeholder">
                <span>▦</span>
                <p>{t.storeHint}</p>
              </div>
            ) : loadingProducts ? (
              <div className="customer-v2-products" aria-busy="true" aria-label={t.loading}>
                {[0, 1, 2].map(i => (
                  <div className="customer-v2-skeleton-product" key={i}>
                    <span className="skeleton" />
                    <div>
                      <span className="skeleton sk-line w-40" />
                      <span className="skeleton sk-line w-80" />
                      <span className="skeleton sk-line w-60" />
                    </div>
                  </div>
                ))}
              </div>
            ) : filteredProducts.length ? (
              <div className="customer-v2-products">
                {filteredProducts.map(product => (
                  <article
                    className="customer-v2-product"
                    key={product.id}
                  >
                    <div className="customer-v2-product-image">
                      {product.image ? (
                        <SafeImage
                          src={product.image}
                          alt={product.name}
                        />
                      ) : (
                        <span>◫</span>
                      )}
                    </div>

                    <div className="customer-v2-product-body">
                      <small>
                        {product.category || activeMerchant?.category || ''}
                      </small>
                      <h3>{product.name}</h3>

                      {product.description && (
                        <p>{product.description}</p>
                      )}

                      <div className="customer-v2-product-footer">
                        <div className="customer-v2-price-stack">
                          <b>{money(product.price)}</b>
                          {stockState(product) === 'out' ? (
                            <small className="stock-badge is-out">{t.outOfStock}</small>
                          ) : stockState(product) === 'low' ? (
                            <small className="stock-badge is-low">
                              {t.lowStock} · {t.stockLeft} {product.quantity}
                            </small>
                          ) : null}
                        </div>
                        <button
                          className={addedId === product.id ? 'is-added' : ''}
                          disabled={isSoldOut(product)}
                          onClick={() => addProduct(product)}
                        >
                          {isSoldOut(product)
                            ? t.outOfStock
                            : addedId === product.id
                              ? t.added
                              : t.add}
                          <span>
                            {isSoldOut(product)
                              ? '✕'
                              : addedId === product.id
                                ? '✓'
                                : '＋'}
                          </span>
                        </button>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="customer-v2-empty">
                {search ? t.searchEmpty : t.noProducts}
              </p>
            )}
          </section>

          <section className="customer-v2-section customer-v2-recent">
            <div className="customer-v2-heading">
              <div>
                <span className="customer-v2-eyebrow">ACTIVITY</span>
                <h2>{t.orders}</h2>
              </div>
            </div>

            {orders.length ? (
              <div className="customer-v2-order-list">
                {orders.map(order => (
                  <div className="customer-v2-order" key={order.id}>
                    <span className="customer-v2-order-icon">↗</span>
                    <div>
                      <b>
                        #{order.id} · {order.merchant_name || 'WASELNI'}
                      </b>
                      <small>
                        {order.dropoff_address || t.orderStatus}
                      </small>
                    </div>
                    <span className={`customer-v2-order-status ${statusTone(order.status)}`}>
                      {ORDER_STATUS[lang][order.status] || order.status}
                    </span>
                    <strong>{money(order.total)}</strong>
                    <small>{t.paymentStatus}: {order.payment_method === 'cash' ? t.cashStatus : t.onlineNotIntegrated}</small>
                    {order.status === 'awaiting_confirmation' && (
                      <button
                        type="button"
                        disabled={confirmingOrderId === order.id}
                        onClick={() => confirmOrderReceipt(order.id)}
                      >
                        {confirmingOrderId === order.id ? t.loading : t.confirmReceipt}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="customer-v2-empty">{t.noOrders}</p>
            )}
            <Link className="customer-v2-track-link" to="/orders">
              {lang === 'ar'
                ? 'عرض حالة الطلبات وتتبع الكابتن على الخريطة ←'
                : lang === 'he'
                  ? 'לצפייה במצב ההזמנות ומעקב השליח במפה ←'
                  : 'View order status and track the captain on the map ←'}
            </Link>
          </section>
        </main>

        <aside className="customer-v2-cart-panel" ref={cartPanelRef} id="customer-cart">
          <div className="customer-v2-cart-title">
            <div>
              <span className="customer-v2-eyebrow">YOUR ORDER</span>
              <h2>{t.cart}</h2>
            </div>

            <div className="customer-v2-cart-title-actions">
              <span className="customer-v2-cart-badge">{cartCount}</span>

              {cart.length > 0 && (
                <button
                  type="button"
                  className="customer-v2-clear"
                  onClick={() => setCart([])}
                >
                  {t.clearCart}
                </button>
              )}
            </div>
          </div>

          <p className="customer-v2-cart-hint">{t.cartHint}</p>

          {cart.length ? (
            <div className="customer-v2-cart-lines">
              {cart.map(line => {
                const limit = stockLimit(line.product);
                return (
                <div
                  className="customer-v2-cart-line"
                  key={line.product.id}
                >
                  <div className="customer-v2-cart-line-main">
                    <b>{line.product.name}</b>
                    <small>
                      {money(line.product.price)}
                      {limit != null && (
                        <span className="customer-v2-line-stock">
                          {' '}· {t.stockLeft} {limit}
                        </span>
                      )}
                    </small>
                  </div>

                  <div className="customer-v2-qty">
                    <button
                      onClick={() =>
                        changeQuantity(line.product.id, -1)
                      }
                      aria-label="Decrease"
                    >
                      −
                    </button>

                    <span>{line.quantity}</span>

                    <button
                      disabled={limit != null && line.quantity >= limit}
                      onClick={() =>
                        changeQuantity(line.product.id, 1)
                      }
                      aria-label="Increase"
                    >
                      ＋
                    </button>
                  </div>
                </div>
                );
              })}

            </div>
          ) : (
            <div className="customer-v2-cart-empty">
              <span>🛍</span>
              <p>{t.empty}</p>
            </div>
          )}

          <div className="customer-v2-totals">
            <div>
              <span>{t.subtotal}</span>
              <b>{money(subtotal)}</b>
            </div>

            <div>
              <span>{t.deliveryFee}</span>
              <b>{money(deliveryFee)}</b>
            </div>
            <div className="customer-v2-grand-total">
              <span>{t.total}</span>
              <strong>{money(subtotal + Number(deliveryFee || 0))}</strong>
            </div>

            <small className="customer-v2-fee-note">
              {t.deliveryFeeNote}
            </small>
          </div>

          <form className="customer-v2-checkout" onSubmit={checkout}>
            <label>
              {t.address}
              <input
                required
                value={address}
                onChange={e => setAddress(e.target.value)}
                placeholder={t.address}
              />
            </label>

            <label>{t.deliveryFee}
              <input type="number" min="0.50" max="500" step="0.50" required value={deliveryFee} onChange={event => setDeliveryFee(event.target.value)}/>
            </label>
            <p className="customer-v2-fee-note">{t.deliveryFeeNote}</p>
            <label>{t.customerLocation}</label>
            <CheckoutLocationMap merchant={activeMerchant} latitude={dropoffLat} longitude={dropoffLng} onSelect={(lat, lng, place) => { setDropoffLat(lat); setDropoffLng(lng); if (place) setAddress(place); }} t={t}/>
            <label>
              {t.notes}
              <textarea
                rows={2}
                value={notes}
                onChange={e => setNotes(e.target.value)}
              />
            </label>

            <div className="customer-v2-payment">
              <span>◉</span>
              <div>
                <b>{t.cash}</b>
                <small>
                  {lang === 'ar'
                    ? 'متاح حالياً'
                    : lang === 'he'
                      ? 'זמין כרגע'
                      : 'Currently available'}
                </small>
              </div>
            </div>

            <button
              className="customer-v2-submit"
              disabled={!cart.length || cartInvalid || !address.trim() || dropoffLat == null || dropoffLng == null || !activeMerchant || activeMerchant.latitude == null || activeMerchant.longitude == null || submitting}
            >
              {submitting ? t.loading : t.placeOrder}
              <span>←</span>
            </button>
          </form>

          {error && (
            <p className="customer-v2-feedback is-error" role="alert">
              {error}
            </p>
          )}

          {notice && (
            <p className="customer-v2-feedback is-success" role="status">
              {notice}
            </p>
          )}
        </aside>

        {cartCount > 0 && (
          <button
            type="button"
            className="customer-v2-cart-fab"
            onClick={() => {
              void revalidateCart(true);
              cartPanelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }}
          >
            <span aria-hidden="true">🛍</span>
            {t.viewCart}
            <b>{cartCount}</b>
          </button>
        )}
      </div>
    </div>
  );
}
