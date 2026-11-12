import { useEffect, useRef, useState } from 'react'

const COPY = {
  ar: { confirm: 'تأكيد', cancel: 'إلغاء' },
  he: { confirm: 'אישור', cancel: 'ביטול' },
  en: { confirm: 'Confirm', cancel: 'Cancel' },
}

let pendingResolve = null

export function confirmAction({ title, message, confirmLabel, cancelLabel }) {
  return new Promise((resolve) => {
    pendingResolve = resolve
    window.dispatchEvent(
      new CustomEvent('waselni:confirm', {
        detail: { title, message, confirmLabel, cancelLabel },
      })
    )
  })
}

export default function ConfirmHost({ lang = 'ar' }) {
  const copy = COPY[lang] || COPY.ar
  const [request, setRequest] = useState(null)
  const confirmButton = useRef(null)

  useEffect(() => {
    const onRequest = (event) => setRequest(event.detail || {})
    window.addEventListener('waselni:confirm', onRequest)
    return () => window.removeEventListener('waselni:confirm', onRequest)
  }, [])

  useEffect(() => {
    if (request) confirmButton.current?.focus()
  }, [request])

  function close(value) {
    const resolve = pendingResolve
    pendingResolve = null
    setRequest(null)
    if (resolve) resolve(value)
  }

  if (!request) return null

  return (
    <div className="pwa-modal-backdrop" role="presentation" onClick={() => close(false)}>
      <section
        className="pwa-modal app-confirm"
        role="dialog"
        aria-modal="true"
        aria-labelledby="app-confirm-title"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => {
          if (event.key === 'Escape') close(false)
        }}
      >
        {request.title && <h2 id="app-confirm-title">{request.title}</h2>}
        {request.message && <p>{request.message}</p>}
        <div className="app-confirm-actions">
          <button type="button" className="secondary" onClick={() => close(false)}>
            {request.cancelLabel || copy.cancel}
          </button>
          <button type="button" ref={confirmButton} onClick={() => close(true)}>
            {request.confirmLabel || copy.confirm}
          </button>
        </div>
      </section>
    </div>
  )
}
