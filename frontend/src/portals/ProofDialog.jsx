import React, { useState } from 'react'
import { api } from '../api'

const needsOtp = order => ['parcel', 'logistics'].includes(order?.service_type)

export default function ProofDialog({ order, t, onClose, onSaved }) {
  const [kind, setKind] = useState('delivery')
  const [otp, setOtp] = useState('')
  const [recipient, setRecipient] = useState('')
  const [notes, setNotes] = useState('')
  const [photo, setPhoto] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function submit(event) {
    event.preventDefault()
    setBusy(true); setError(''); setNotice('')
    try {
      const body = new FormData()
      body.append('kind', kind)
      if (otp) body.append('otp', otp)
      if (recipient) body.append('recipient_name', recipient)
      if (notes) body.append('notes', notes)
      if (photo) body.append('photo', photo)
      await api(`/orders/${order.id}/proof/`, { method: 'POST', body })
      setNotice(t.proofSaved)
      await onSaved?.()
      onClose?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label={t.proofTitle}>
    <section className="modal-card">
      <div className="section-head"><div><h3>{t.proofTitle}</h3><p>{t.proofHint} · {order.order_number}</p></div>
        <button type="button" className="secondary" onClick={onClose} aria-label={t.cancel}>×</button></div>
      <form className="form-stack" onSubmit={submit}>
        <label>{t.proofKind}<select value={kind} onChange={e => setKind(e.target.value)}>
          <option value="pickup">{t.proofPickup}</option>
          <option value="delivery">{t.proofDelivery}</option>
        </select></label>
        {kind === 'delivery' && needsOtp(order) && <label>{t.deliveryCode}
          <input value={otp} onChange={e => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))} inputMode="numeric" placeholder="000000" required/>
        </label>}
        {kind === 'delivery' && <label>{t.recipientName}
          <input value={recipient} onChange={e => setRecipient(e.target.value)} maxLength={150}/>
        </label>}
        <label>{t.proofPhoto}{needsOtp(order) && kind === 'delivery' ? ` · ${t.required}` : ` · ${t.optional}`}
          <input type="file" accept="image/jpeg,image/png,image/webp" onChange={e => setPhoto(e.target.files?.[0] || null)} required={needsOtp(order) && kind === 'delivery'}/>
        </label>
        <label>{t.notes}<textarea rows="3" value={notes} onChange={e => setNotes(e.target.value)} maxLength={500}/></label>
        {error && <p className="error">{error}</p>}
        {notice && <p className="success-note">{notice}</p>}
        <div className="row-actions">
          <button type="submit" disabled={busy}>{busy ? t.saving : t.saveProof}</button>
          <button type="button" className="secondary" onClick={onClose}>{t.cancel}</button>
        </div>
      </form>
    </section>
  </div>
}
