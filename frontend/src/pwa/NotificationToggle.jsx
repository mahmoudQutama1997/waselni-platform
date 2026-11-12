import { useEffect, useState } from 'react'
import {
  notificationPermission,
  notificationsSupported,
  requestNotificationPermission,
} from './alerts.js'

const COPY = {
  ar: {
    title: 'إشعارات الطلبات',
    enable: 'تفعيل الإشعارات',
    enabled: 'الإشعارات مفعّلة',
    blocked: 'الإشعارات محجوبة. اسمح بها من إعدادات المتصفح لهذا الموقع.',
    unsupported: 'هذا المتصفح لا يدعم إشعارات النظام. تظهر التنبيهات داخل التطبيق فقط.',
    ios: 'على iPhone وiPad، ثبّت التطبيق على الشاشة الرئيسية أولاً ثم فعّل الإشعارات.',
    note: 'تصلك تنبيهات الطلبات الجديدة حتى عندما يكون التطبيق في الخلفية، مع صوت تنبيه داخل التطبيق.',
    denied: 'لم يتم منح إذن الإشعارات.',
  },
  he: {
    title: 'התראות הזמנות',
    enable: 'הפעלת התראות',
    enabled: 'התראות פעילות',
    blocked: 'ההתראות חסומות. יש לאשר אותן בהגדרות הדפדפן עבור האתר.',
    unsupported: 'הדפדפן אינו תומך בהתראות מערכת. ההתראות יוצגו בתוך האפליקציה בלבד.',
    ios: 'ב-iPhone וב-iPad יש להתקין תחילה את האפליקציה במסך הבית ואז להפעיל התראות.',
    note: 'קבלו התראות על הזמנות חדשות גם כשהאפליקציה ברקע, עם צליל התראה בתוך האפליקציה.',
    denied: 'ההרשאה להתראות לא ניתנה.',
  },
  en: {
    title: 'Order notifications',
    enable: 'Enable notifications',
    enabled: 'Notifications enabled',
    blocked: 'Notifications are blocked. Allow them in the browser settings for this site.',
    unsupported: 'This browser does not support system notifications. Alerts appear inside the app only.',
    ios: 'On iPhone and iPad, install the app to the home screen first, then enable notifications.',
    note: 'Get new-order notifications while the app is in the background, with an in-app alert sound.',
    denied: 'Notification permission was not granted.',
  },
}

function standalone() {
  return (
    window.matchMedia?.('(display-mode: standalone)').matches ||
    window.navigator.standalone === true
  )
}

export default function NotificationToggle({ lang = 'ar' }) {
  const copy = COPY[lang] || COPY.ar
  const [permission, setPermission] = useState(notificationPermission)
  const [support] = useState(notificationsSupported)
  const [message, setMessage] = useState('')
  const [isIos] = useState(() => /iphone|ipad|ipod/i.test(navigator.userAgent))
  const [isStandalone, setIsStandalone] = useState(standalone)

  useEffect(() => {
    const media = window.matchMedia?.('(display-mode: standalone)')
    const onChange = () => setIsStandalone(standalone())
    media?.addEventListener?.('change', onChange)
    return () => media?.removeEventListener?.('change', onChange)
  }, [])

  const iosBlocked = isIos && !isStandalone

  async function enable() {
    const result = await requestNotificationPermission()
    setPermission(result)
    setMessage(result === 'denied' ? copy.denied : '')
  }

  let status = copy.note
  if (!support) status = copy.unsupported
  else if (permission === 'denied') status = copy.blocked
  else if (iosBlocked) status = copy.ios

  return (
    <section className="panel notification-settings">
      <div className="section-head">
        <div>
          <h3>{copy.title}</h3>
          <p>{status}</p>
        </div>
      </div>
      {support && permission !== 'granted' && !iosBlocked && (
        <button type="button" onClick={enable}>{copy.enable}</button>
      )}
      {permission === 'granted' && <span className="tag ready">{copy.enabled}</span>}
      {message && <p className="error">{message}</p>}
    </section>
  )
}
