import { NavLink } from 'react-router-dom'
import { MOBILE_NAV } from './roles.js'
import NavIcon from './navIcons.jsx'

export default function MobileNav({ role, t }) {
  const items = MOBILE_NAV[role] || MOBILE_NAV.all

  return (
    <nav className="mobile-tabbar" aria-label={t.navigation || t.home}>
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) => `mobile-tab${isActive ? ' active' : ''}`}
        >
          <NavIcon name={item.icon} />
          <span>{t[item.labelKey] || item.labelKey}</span>
        </NavLink>
      ))}
    </nav>
  )
}
