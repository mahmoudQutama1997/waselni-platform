import { NavLink } from 'react-router-dom'
import { MOBILE_NAV } from './roles.js'
import NavIcon from './navIcons.jsx'

const SHORT_LABELS = {
  catalog: 'catalogShort',
  reports: 'reportsShort',
  settlements: 'settlementsShort',
  accountProfile: 'accountShort',
}

export default function MobileNav({ role, t }) {
  const items = MOBILE_NAV[role] || MOBILE_NAV.all

  return (
    <nav className="mobile-tabbar" aria-label={t.navigation || t.home}>
      {items.map((item) => {
        const shortKey = SHORT_LABELS[item.labelKey]
        const label = (shortKey && t[shortKey]) || t[item.labelKey] || item.labelKey
        return (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) => `mobile-tab${isActive ? ' active' : ''}`}
          >
            <NavIcon name={item.icon} />
            <span>{label}</span>
          </NavLink>
        )
      })}
    </nav>
  )
}
