let audioContext = null
let unlocked = false

export function unlockAlertAudio() {
  if (unlocked) return
  const AudioCtor = window.AudioContext || window.webkitAudioContext
  if (!AudioCtor) return
  try {
    audioContext = audioContext || new AudioCtor()
    if (audioContext.state === 'suspended') audioContext.resume()
    unlocked = true
  } catch {
    unlocked = false
  }
}

function beep(frequency, startAt, duration = 0.16, volume = 0.12) {
  if (!audioContext) return
  const oscillator = audioContext.createOscillator()
  const gain = audioContext.createGain()
  oscillator.type = 'sine'
  oscillator.frequency.value = frequency
  gain.gain.setValueAtTime(0.0001, startAt)
  gain.gain.exponentialRampToValueAtTime(volume, startAt + 0.02)
  gain.gain.exponentialRampToValueAtTime(0.0001, startAt + duration)
  oscillator.connect(gain)
  gain.connect(audioContext.destination)
  oscillator.start(startAt)
  oscillator.stop(startAt + duration + 0.02)
}

/** Short in-app chime for new merchant/captain orders. Requires prior user interaction. */
export function playOrderAlert() {
  if (!unlocked || !audioContext) return
  if (audioContext.state === 'suspended') audioContext.resume().catch(() => {})
  const now = audioContext.currentTime
  beep(880, now, 0.14, 0.1)
  beep(1174, now + 0.19, 0.16, 0.12)
  beep(1568, now + 0.4, 0.2, 0.1)
}

export function notificationsSupported() {
  return typeof window !== 'undefined' && 'Notification' in window
}

export function notificationPermission() {
  return notificationsSupported() ? Notification.permission : 'unsupported'
}

export async function requestNotificationPermission() {
  if (!notificationsSupported()) return 'unsupported'
  try {
    return await Notification.requestPermission()
  } catch {
    return Notification.permission
  }
}

export function showOrderNotification(title, body, tag) {
  if (!notificationsSupported() || Notification.permission !== 'granted') return false
  if (document.visibilityState === 'visible') return false
  try {
    const notification = new Notification(title, {
      body,
      tag,
      icon: '/icons/icon-192.png',
      badge: '/icons/favicon-32.png',
      silent: true,
    })
    notification.onclick = () => {
      window.focus()
      notification.close()
    }
    return true
  } catch {
    return false
  }
}
