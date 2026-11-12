import { useEffect, useState } from 'react'
import { applyServiceWorkerUpdate, watchForServiceWorkerUpdate } from './registerSW.js'

const DISMISS_KEY = 'waselni_install_dismissed_until'
const DISMISS_MS = 7 * 24 * 60 * 60 * 1000

const COPY = {
  ar: {
    installTitle: 'ثبّت تطبيق وصلني',
    installBody: 'أضف التطبيق إلى شاشتك الرئيسية للوصول السريع وتجربة ملء الشاشة.',
    install: 'تثبيت',
    iosInstall: 'طريقة التثبيت',
    later: 'لاحقاً',
    iosTitle: 'تثبيت وصلني على iPhone أو iPad',
    iosSteps: [
      'افتح التطبيق في متصفح Safari.',
      'اضغط زر المشاركة في شريط Safari.',
      'اختر «إضافة إلى الشاشة الرئيسية» ثم «إضافة».',
    ],
    iosNote: 'يتوفر التثبيت على iPhone وiPad عبر Safari فقط.',
    understood: 'فهمت',
    updateTitle: 'إصدار جديد متوفر',
    updateBody: 'تم تجهيز تحديث وصلني. أعد التحميل لتطبيق أحدث نسخة.',
    reload: 'تحديث الآن',
    offlineTitle: 'لا يوجد اتصال بالإنترنت',
    offlineBody: 'ستُحدَّث الطلبات فور عودة الاتصال. لا تُحفظ بيانات الطلبات دون اتصال.',
    close: 'إغلاق',
  },
  he: {
    installTitle: 'התקנת אפליקציית Waselni',
    installBody: 'הוסיפו את האפליקציה למסך הבית לגישה מהירה וחוויית מסך מלא.',
    install: 'התקנה',
    iosInstall: 'איך מתקינים',
    later: 'אחר כך',
    iosTitle: 'התקנה ב-iPhone או iPad',
    iosSteps: [
      'פתחו את האפליקציה בדפדפן Safari.',
      'הקישו על כפתור השיתוף בסרגל Safari.',
      'בחרו «הוסף למסך הבית» ואז «הוסף».',
    ],
    iosNote: 'ההתקנה ב-iPhone וב-iPad זמינה דרך Safari בלבד.',
    understood: 'הבנתי',
    updateTitle: 'גרסה חדשה זמינה',
    updateBody: 'עדכון Waselni מוכן. רעננו כדי להפעיל את הגרסה החדשה.',
    reload: 'עדכן עכשיו',
    offlineTitle: 'אין חיבור לאינטרנט',
    offlineBody: 'ההזמנות יתעדכנו כשהחיבור יחזור. נתוני הזמנות אינם נשמרים ללא חיבור.',
    close: 'סגירה',
  },
  en: {
    installTitle: 'Install Waselni',
    installBody: 'Add the app to your home screen for quick access and a full-screen experience.',
    install: 'Install',
    iosInstall: 'How to install',
    later: 'Later',
    iosTitle: 'Install Waselni on iPhone or iPad',
    iosSteps: [
      'Open the app in Safari.',
      'Tap the Share button in the Safari toolbar.',
      'Choose “Add to Home Screen”, then tap “Add”.',
    ],
    iosNote: 'On iPhone and iPad, installation is available through Safari only.',
    understood: 'Got it',
    updateTitle: 'A new version is available',
    updateBody: 'A Waselni update is ready. Reload to run the latest version.',
    reload: 'Update now',
    offlineTitle: 'You are offline',
    offlineBody: 'Orders refresh when the connection returns. Order data is never stored for offline use.',
    close: 'Close',
  },
}

function isStandalone() {
  if (typeof window === 'undefined') return false
  return (
    window.matchMedia?.('(display-mode: standalone)').matches ||
    window.navigator.standalone === true
  )
}

function isIosDevice() {
  if (typeof navigator === 'undefined') return false
  return /iphone|ipad|ipod/i.test(navigator.userAgent)
}

export default function PwaBanners({ lang = 'ar' }) {
  const copy = COPY[lang] || COPY.ar
  const [installEvent, setInstallEvent] = useState(null)
  const [iosOpen, setIosOpen] = useState(false)
  const [updateReady, setUpdateReady] = useState(false)
  const [online, setOnline] = useState(typeof navigator === 'undefined' ? true : navigator.onLine)
  const [installed, setInstalled] = useState(isStandalone)
  const [dismissed, setDismissed] = useState(() => {
    try {
      return Number(localStorage.getItem(DISMISS_KEY) || 0) > Date.now()
    } catch {
      return false
    }
  })

  useEffect(() => {
    const onPrompt = (event) => {
      event.preventDefault()
      setInstallEvent(event)
    }
    const onInstalled = () => {
      setInstalled(true)
      setInstallEvent(null)
    }
    const onOnline = () => setOnline(true)
    const onOffline = () => setOnline(false)

    window.addEventListener('beforeinstallprompt', onPrompt)
    window.addEventListener('appinstalled', onInstalled)
    window.addEventListener('online', onOnline)
    window.addEventListener('offline', onOffline)
    const stopWatching = watchForServiceWorkerUpdate(() => setUpdateReady(true))

    const media = window.matchMedia?.('(display-mode: standalone)')
    const onDisplayChange = (event) => setInstalled(event.matches || window.navigator.standalone === true)
    media?.addEventListener?.('change', onDisplayChange)

    return () => {
      window.removeEventListener('beforeinstallprompt', onPrompt)
      window.removeEventListener('appinstalled', onInstalled)
      window.removeEventListener('online', onOnline)
      window.removeEventListener('offline', onOffline)
      stopWatching()
      media?.removeEventListener?.('change', onDisplayChange)
    }
  }, [])

  useEffect(() => {
    if (!iosOpen) return undefined
    const onKey = (event) => {
      if (event.key === 'Escape') setIosOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [iosOpen])

  async function install() {
    if (!installEvent) {
      setIosOpen(true)
      return
    }
    installEvent.prompt()
    const choice = await installEvent.userChoice.catch(() => null)
    setInstallEvent(null)
    if (choice?.outcome === 'accepted') setInstalled(true)
  }

  function dismissInstall() {
    setDismissed(true)
    try {
      localStorage.setItem(DISMISS_KEY, String(Date.now() + DISMISS_MS))
    } catch {
      /* storage may be unavailable in private mode */
    }
  }

  function reloadForUpdate() {
    applyServiceWorkerUpdate()
    window.setTimeout(() => window.location.reload(), 1200)
  }

  const canInstall = !installed && !dismissed && (installEvent || isIosDevice())

  if (!updateReady && online && !canInstall) return null

  return (
    <>
      <div className="pwa-stack">
        {updateReady && (
          <section className="pwa-banner pwa-update" role="status" aria-live="polite">
            <div>
              <strong>{copy.updateTitle}</strong>
              <p>{copy.updateBody}</p>
            </div>
            <div className="pwa-actions">
              <button type="button" onClick={reloadForUpdate}>{copy.reload}</button>
            </div>
          </section>
        )}

        {!online && (
          <section className="pwa-banner pwa-offline" role="alert">
            <div>
              <strong>{copy.offlineTitle}</strong>
              <p>{copy.offlineBody}</p>
            </div>
          </section>
        )}

        {canInstall && online && (
          <section className="pwa-banner pwa-install" role="region" aria-label={copy.installTitle}>
            <div className="pwa-install-mark" aria-hidden="true">و</div>
            <div className="pwa-install-copy">
              <strong>{copy.installTitle}</strong>
              <p>{copy.installBody}</p>
            </div>
            <div className="pwa-actions">
              <button type="button" onClick={install}>{installEvent ? copy.install : copy.iosInstall}</button>
              <button type="button" className="ghost" onClick={dismissInstall}>{copy.later}</button>
            </div>
            <button type="button" className="pwa-dismiss" onClick={dismissInstall} aria-label={copy.close}>×</button>
          </section>
        )}
      </div>

      {iosOpen && (
        <div className="pwa-modal-backdrop" role="presentation" onClick={() => setIosOpen(false)}>
          <section
            className="pwa-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="pwa-ios-title"
            onClick={(event) => event.stopPropagation()}
          >
            <h2 id="pwa-ios-title">{copy.iosTitle}</h2>
            <ol>
              {copy.iosSteps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
            <p className="muted-note">{copy.iosNote}</p>
            <button type="button" onClick={() => setIosOpen(false)}>{copy.understood}</button>
          </section>
        </div>
      )}
    </>
  )
}
