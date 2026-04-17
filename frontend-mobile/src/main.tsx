import React from 'react'
import ReactDOM from 'react-dom/client'
import './styles/tokens.css'
import './styles/animations.css'
import App from './App'
import { extractAndStoreBackendUrl } from './utils/backend'

// Read ?b=<backendUrl> from the QR code URL (hybrid deployment) and persist to
// sessionStorage before any React rendering so the very first API call uses it.
extractAndStoreBackendUrl()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
