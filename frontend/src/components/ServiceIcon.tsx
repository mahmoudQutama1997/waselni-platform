import type { ReactNode } from 'react'

export type ServiceIconName =
  | 'vespa'
  | 'car'
  | 'truck'
  | 'store'
  | 'parcel'
  | 'orders'
  | 'money'
  | 'support'

const PATHS: Record<ServiceIconName, ReactNode> = {
  vespa: (
    <>
      <circle cx="5.6" cy="17.2" r="2.8" />
      <circle cx="18.4" cy="17.2" r="2.8" />
      <path d="M8.4 17.2h5.4" />
      <path d="M13.8 17.2 15.2 9h2.6" />
      <path d="M14.6 9h3.6" />
      <path d="M8.6 12.6h4.2v4.6" />
    </>
  ),
  car: (
    <>
      <path d="M3.5 16.5v-3.1l1.8-4.6A2 2 0 0 1 7.2 7.5h9.6a2 2 0 0 1 1.9 1.3l1.8 4.6v3.1" />
      <path d="M3.5 13.4h17" />
      <circle cx="7.4" cy="17.6" r="1.7" />
      <circle cx="16.6" cy="17.6" r="1.7" />
    </>
  ),
  truck: (
    <>
      <path d="M2.5 6.5h10.5v10H2.5z" />
      <path d="M13 9.5h3.4l3.1 3.1v3.9H13" />
      <circle cx="6.6" cy="18.2" r="2" />
      <circle cx="17.4" cy="18.2" r="2" />
      <path d="M8.6 18.2h6.8" />
    </>
  ),
  store: (
    <>
      <path d="M4 10h16l-1.5-5.2A1 1 0 0 0 17.6 4H6.4a1 1 0 0 0-1 .8L4 10Z" />
      <path d="M5 10v9h14v-9" />
      <path d="M9.5 19v-5.2h5V19" />
    </>
  ),
  parcel: (
    <>
      <path d="M12 3 4.5 7v10L12 21l7.5-4V7z" />
      <path d="M4.5 7 12 11l7.5-4M12 11v10" />
      <path d="M8.2 5 15.7 9" />
    </>
  ),
  orders: (
    <>
      <rect x="5" y="3" width="14" height="18" rx="2" />
      <path d="M8 8h8M8 12h8M8 16h5" />
    </>
  ),
  money: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M15 8.5c-.7-.7-1.7-1-3-1-1.7 0-3 .8-3 2s1.2 1.8 3 2.2 3 1 3 2.3-1.3 2.2-3 2.2c-1.2 0-2.4-.4-3.2-1.2M12 5.5v13" />
    </>
  ),
  support: (
    <>
      <path d="M4 5h16v12H8l-4 4z" />
      <path d="M8 9h8M8 13h5" />
    </>
  )
}

const ALIASES: Record<string, ServiceIconName> = {
  motorcycle: 'vespa',
  ride: 'vespa',
  shipping: 'truck'
}

type Props = {
  name: ServiceIconName | 'motorcycle' | 'ride' | 'shipping'
  size?: 'sm' | 'md' | 'lg'
  label?: string
  className?: string
}

export default function ServiceIcon({
  name,
  size = 'md',
  label,
  className = ''
}: Props) {
  const key = ALIASES[name] || name
  const paths = PATHS[key] || PATHS.store
  return (
    <span
      className={`svc-icon svc-icon--${key} svc-icon--${size} ${className}`.trim()}
      {...(label
        ? { role: 'img', 'aria-label': label }
        : { 'aria-hidden': 'true' })}
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {paths}
      </svg>
    </span>
  )
}
