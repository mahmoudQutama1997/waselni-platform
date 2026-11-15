import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import { api, orderSocket } from '../api'
import { showOrderNotification } from './alerts.js'

const COPY = {
  ar: {
    title: 'الإشعارات',
    markAll: 'تحديد الكل كمقروء',
    empty: 'لا توجد إشعارات بعد',
    loading: 'جارٍ تحميل الإشعارات...',
    error: 'تعذر تحميل الإشعارات',
    retry: 'إعادة المحاولة',
    unreadLabel: 'إشعارات غير مقروءة',
    newOrder: id => `طلب جديد #${id}`,
    orderAccepted: id => `تم قبول طلبك #${id}`,
    orderReady: id => `طلبك #${id} جاهز للاستلام`,
    orderAssigned: id => `تم تعيين كابتن للطلب #${id}`,
    orderStatus: (id, status) => `تحديث الطلب #${id}: ${status}`,
    orderCancelled: id => `تم إلغاء الطلب #${id}`,
    orderAvailable: id => `طلب جديد متاح لك #${id}`,
    stockLow: (name, q) => `كمية منخفضة: ${name} — المتبقي ${q}`,
    stockOutMerchant: name => `نفد مخزون: ${name}`,
    stockOutCustomer: name => `نفد منتج من سلتك: ${name}`,
    customer: 'الزبون',
    items: 'منتج',
    total: 'الإجمالي',
  },
  he: {
    title: 'התראות',
    markAll: 'סימון הכול כנקרא',
    empty: 'אין התראות עדיין',
    loading: 'טוען התראות...',
    error: 'לא ניתן לטעון התראות',
    retry: 'נסה שוב',
    unreadLabel: 'התראות שלא נקראו',
    newOrder: id => `הזמנה חדשה #${id}`,
    orderAccepted: id => `ההזמנה שלך אושרה #${id}`,
    orderReady: id => `ההזמנה שלך מוכנה לאיסוף #${id}`,
    orderAssigned: id => `שליח שובץ להזמנה #${id}`,
    orderStatus: (id, status) => `עדכון הזמנה #${id}: ${status}`,
    orderCancelled: id => `ההזמנה בוטלה #${id}`,
    orderAvailable: id => `הזמנה חדשה זמינה לך #${id}`,
    stockLow: (name, q) => `מלאי נמוך: ${name} — נותרו ${q}`,
    stockOutMerchant: name => `אזל מהמלאי: ${name}`,
    stockOutCustomer: name => `מוצר בסל שלך אזל: ${name}`,
    customer: 'לקוח',
    items: 'מוצרים',
    total: 'סה״כ',
  },
  en: {
    title: 'Notifications',
    markAll: 'Mark all as read',
    empty: 'No notifications yet',
    loading: 'Loading notifications...',
    error: 'Could not load notifications',
    retry: 'Retry',
    unreadLabel: 'unread notifications',
    newOrder: id => `New order #${id}`,
    orderAccepted: id => `Your order was accepted #${id}`,
    orderReady: id => `Your order is ready for pickup #${id}`,
    orderAssigned: id => `A captain was assigned to order #${id}`,
    orderStatus: (id, status) => `Order #${id} updated: ${status}`,
    orderCancelled: id => `Order #${id} was cancelled`,
    orderAvailable: id => `New order available to you #${id}`,
    stockLow: (name, q) => `Low stock: ${name} — ${q} left`,
    stockOutMerchant: name => `Out of stock: ${name}`,
    stockOutCustomer: name => `An item in your cart sold out: ${name}`,
    customer: 'Customer',
    items: 'items',
    total: 'Total',
  },
}

const STATUS_LABELS = {
  ar: { picked_up: 'تم الاستلام', delivering: 'قيد التوصيل', completed: 'مكتمل', preparing: 'قيد التجهيز' },
  he: { picked_up: 'נאסף', delivering: 'במשלוח', completed: 'הושלם', preparing: 'בהכנה' },
  en: { picked_up: 'Picked up', delivering: 'Delivering', completed: 'Completed', preparing: 'Preparing' },
}

function describe(notification, lang, role) {
  const copy = COPY[lang] || COPY.ar
  const statusLabels = STATUS_LABELS[lang] || STATUS_LABELS.ar
  const orderId = notification.order
  const payload = notification.payload || {}
  switch (notification.event) {
    case 'order.created': {
      const parts = []
      if (payload.customer_name) parts.push(`${copy.customer}: ${payload.customer_name}`)
      if (payload.items_count) parts.push(`${payload.items_count} ${copy.items}`)
      if (payload.total) parts.push(`${copy.total}: ${Number(payload.total).toFixed(2)} ₪`)
      return { title: copy.newOrder(orderId), body: parts.join(' · ') }
    }
    case 'order.accepted':
      return { title: copy.orderAccepted(orderId), body: '' }
    case 'order.ready':
      return { title: copy.orderReady(orderId), body: '' }
    case 'order.assigned':
      return { title: copy.orderAssigned(orderId), body: '' }
    case 'order.status': {
      const label = statusLabels[payload.status] || payload.status || ''
      return { title: copy.orderStatus(orderId, label), body: '' }
    }
    case 'order.cancelled':
      return { title: copy.orderCancelled(orderId), body: '' }
    case 'order.available':
      return { title: copy.orderAvailable(orderId), body: '' }
    case 'stock.low':
      return { title: copy.stockLow(payload.name || '', payload.quantity ?? 0), body: '' }
    case 'stock.out':
      if (role === 'customer') {
        const names = (payload.products || []).map(row => row.name).filter(Boolean)
        return { title: copy.stockOutCustomer(payload.name || names.join(', ')), body: '' }
      }
      return { title: copy.stockOutMerchant(payload.name || ''), body: '' }
    default:
      return { title: copy.title, body: '' }
  }
}

function formatTime(value, lang) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const now = new Date()
  const sameDay = date.toDateString() === now.toDateString()
  try {
    return sameDay
      ? new Intl.DateTimeFormat(lang, { hour: '2-digit', minute: '2-digit' }).format(date)
      : new Intl.DateTimeFormat(lang, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }).format(date)
  } catch {
    return date.toLocaleString()
  }
}

export default function NotificationCenter({ lang = 'ar', role }) {
  const copy = COPY[lang] || COPY.ar
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [rows, setRows] = useState([])
  const [unread, setUnread] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [freshId, setFreshId] = useState(null)
  const rootRef = useRef(null)
  const panelRef = useRef(null)
  const knownRef = useRef(new Set())
  const [panelPos, setPanelPos] = useState(null)

  const load = useCallback(async () => {
    try {
      const data = await api('/notifications/')
      const list = Array.isArray(data) ? data : data.results || []
      knownRef.current = new Set(list.map(row => row.id))
      setRows(list)
      setUnread(typeof data.unread === 'number' ? data.unread : list.filter(row => !row.is_read).length)
      setError('')
    } catch (e) {
      setError(e.message || copy.error)
    } finally {
      setLoading(false)
    }
  }, [copy.error])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const push = notification => {
      if (!notification || !notification.id) return
      // A websocket event may arrive before or after a REST reload; keep one row per id.
      if (knownRef.current.has(notification.id)) return
      knownRef.current.add(notification.id)
      const text = describe(notification, lang, role)
      setRows(old => [notification, ...old].slice(0, 100))
      if (!notification.is_read) setUnread(count => count + 1)
      setFreshId(notification.id)
      window.setTimeout(() => setFreshId(current => (current === notification.id ? null : current)), 4000)
      // useOrderAlerts already raises the system notification for these two events;
      // showing another one here would double-alert the same order.
      const handledElsewhere =
        (role === 'merchant' && notification.event === 'order.created') ||
        (role === 'captain' && notification.event === 'order.available')
      if (document.visibilityState === 'hidden' && !handledElsewhere) {
        showOrderNotification(text.title, text.body || copy.title, `notification-${notification.id}`)
      }
    }
    const socket = orderSocket(message => {
      if (message?.type === 'notification.created' && message.notification) push(message.notification)
    })
    const onRealtime = event => { if (event.detail?.connected) load() }
    window.addEventListener('waselni:realtime', onRealtime)
    return () => {
      socket?.close()
      window.removeEventListener('waselni:realtime', onRealtime)
    }
  }, [lang, role, load, copy.title])

  useEffect(() => {
    if (!open) return undefined
    const onPointer = event => {
      if (rootRef.current?.contains(event.target)) return
      if (panelRef.current?.contains(event.target)) return
      setOpen(false)
    }
    const onKey = event => { if (event.key === 'Escape') setOpen(false) }
    const dismiss = () => setOpen(false)
    document.addEventListener('pointerdown', onPointer)
    document.addEventListener('keydown', onKey)
    window.addEventListener('resize', dismiss)
    window.addEventListener('scroll', dismiss, true)
    return () => {
      document.removeEventListener('pointerdown', onPointer)
      document.removeEventListener('keydown', onKey)
      window.removeEventListener('resize', dismiss)
      window.removeEventListener('scroll', dismiss, true)
    }
  }, [open])

  function togglePanel() {
    if (open) {
      setOpen(false)
      return
    }
    const rect = rootRef.current?.getBoundingClientRect()
    if (rect) {
      const width = Math.min(380, window.innerWidth - 16)
      let left = document.documentElement.dir === 'rtl' ? rect.left : rect.right - width
      left = Math.min(Math.max(8, left), window.innerWidth - width - 8)
      setPanelPos({ top: Math.round(rect.bottom + 8), left: Math.round(left), width })
    }
    setOpen(true)
  }

  async function markRead(row) {
    if (row.is_read) return
    setRows(old => old.map(item => (item.id === row.id ? { ...item, is_read: true } : item)))
    setUnread(count => Math.max(0, count - 1))
    try {
      await api(`/notifications/${row.id}/read/`, { method: 'POST' })
    } catch {
      load()
    }
  }

  async function markAll() {
    if (!unread) return
    setRows(old => old.map(item => ({ ...item, is_read: true })))
    setUnread(0)
    try {
      await api('/notifications/read-all/', { method: 'POST' })
    } catch {
      load()
    }
  }

  function openRow(row) {
    markRead(row)
    setOpen(false)
    if (row.event.startsWith('stock.')) {
      navigate(role === 'merchant' ? '/catalog' : role === 'admin' ? '/admin' : '/')
    } else {
      navigate('/orders')
    }
  }

  return (
    <div className="notif-center" ref={rootRef}>
      <button
        type="button"
        className={`notif-bell ${unread ? 'has-unread' : ''}`}
        aria-label={unread ? `${copy.title} · ${unread} ${copy.unreadLabel}` : copy.title}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={togglePanel}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d="M12 3a6 6 0 0 0-6 6v3.2l-1.4 2.8a1 1 0 0 0 .9 1.5h13a1 1 0 0 0 .9-1.5L18 12.2V9a6 6 0 0 0-6-6Z" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
          <path d="M9.6 19a2.6 2.6 0 0 0 4.8 0" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
        </svg>
        {unread > 0 && <span className="notif-badge">{unread > 99 ? '99+' : unread}</span>}
      </button>
      {open && createPortal(
        <div
          className="notif-dropdown"
          role="menu"
          aria-label={copy.title}
          ref={panelRef}
          style={panelPos ? { top: panelPos.top, left: panelPos.left, width: panelPos.width } : undefined}
        >
          <div className="notif-head">
            <div>
              <b>{copy.title}</b>
              {unread > 0 && <small>{unread} {copy.unreadLabel}</small>}
            </div>
            {unread > 0 && <button type="button" className="secondary notif-mark-all" onClick={markAll}>{copy.markAll}</button>}
          </div>
          <div className="notif-list">
            {loading && <p className="muted-note notif-state">{copy.loading}</p>}
            {!loading && error && (
              <p className="error notif-state">{copy.error} <button type="button" className="secondary" onClick={load}>{copy.retry}</button></p>
            )}
            {!loading && !error && !rows.length && <p className="muted-note notif-state">{copy.empty}</p>}
            {!loading && !error && rows.map(row => {
              const text = describe(row, lang, role)
              return (
                <button
                  type="button"
                  role="menuitem"
                  key={row.id}
                  className={`notif-item ${row.is_read ? '' : 'is-unread'} ${freshId === row.id ? 'is-fresh' : ''}`}
                  onClick={() => openRow(row)}
                >
                  <span className="notif-dot" aria-hidden="true" />
                  <span className="notif-copy">
                    <b>{text.title}</b>
                    {text.body && <small>{text.body}</small>}
                    <time dateTime={row.created_at}>{formatTime(row.created_at, lang)}</time>
                  </span>
                </button>
              )
            })}
          </div>
        </div>,
        document.body
      )}
    </div>
  )
}
