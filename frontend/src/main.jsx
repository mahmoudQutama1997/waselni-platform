import React from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, HashRouter } from 'react-router-dom'
import App from './App'
import { isNativePlatform } from './platform'
import './style.css'
import './tailwind.css'
import './design.css'
import { registerServiceWorker } from './pwa/registerSW.js'

const native = isNativePlatform()
const Router = native ? HashRouter : BrowserRouter

if (native) {
  // A Capacitor shell loads from capacitor://localhost, where the web service
  // worker cannot be served. Remove any stale registration from earlier builds.
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.getRegistrations()
      .then(registrations => registrations.forEach(registration => registration.unregister()))
      .catch(() => {})
  }
} else {
  registerServiceWorker()
}

createRoot(document.getElementById('root')).render(<Router><App /></Router>)
