import { useState, useEffect, useRef } from 'react'
import { AVATAR_ICONS } from '../../types/game'
import './OnboardingForm.css'

interface JoinedSession {
  game_id: string
  player_id: string
  session_token: string
  permanent_id: string
}

interface Props {
  prefillCode: string
  permanentId: string | null
  onJoined: (session: JoinedSession) => void
  savedSession?: { game_id: string } | null
  onRejoin?: () => void
}

const PERMANENT_ID_KEY = 'ww_permanent_id'
const PHOTO_URL_KEY = 'ww_photo_url'

/** Resize a File to at most maxPx × maxPx and return as a JPEG Blob. */
function resizeImage(file: File, maxPx = 256): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    const url = URL.createObjectURL(file)
    img.onload = () => {
      const ratio = Math.min(maxPx / img.width, maxPx / img.height, 1)
      const w = Math.round(img.width * ratio)
      const h = Math.round(img.height * ratio)
      const canvas = document.createElement('canvas')
      canvas.width = w
      canvas.height = h
      canvas.getContext('2d')!.drawImage(img, 0, 0, w, h)
      URL.revokeObjectURL(url)
      canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('toBlob failed')), 'image/jpeg', 0.82)
    }
    img.onerror = reject
    img.src = url
  })
}

/** Returns true when running inside an iOS in-app browser (WKWebView / SFSafariViewController).
 *  These contexts have isolated localStorage — switching to Safari loses the session.  */
function isIosInAppBrowser(): boolean {
  const ua = navigator.userAgent
  const isIos = /iphone|ipad|ipod/i.test(ua)
  if (!isIos) return false
  // Safari on iOS includes "Safari/" in its UA; in-app browsers typically don't
  const hasSafari = /safari/i.test(ua)
  const hasChrome = /crios/i.test(ua)   // Chrome for iOS
  const hasFirefox = /fxios/i.test(ua)  // Firefox for iOS
  return !(hasSafari || hasChrome || hasFirefox)
}

export default function OnboardingForm({ prefillCode, permanentId, onJoined, savedSession, onRejoin }: Props) {
  const [name, setName] = useState('')
  const [code, setCode] = useState(prefillCode.toUpperCase())
  const inAppBrowser = isIosInAppBrowser()
  const [avatarId, setAvatarId] = useState('icon_00')
  const [photoUrl, setPhotoUrl] = useState<string | null>(() => localStorage.getItem(PHOTO_URL_KEY))
  const [photoPreview, setPhotoPreview] = useState<string | null>(null)
  const [photoUploading, setPhotoUploading] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // resolvedPermanentId is only set if the GET confirms the player exists in the DB.
  // A stale localStorage entry (e.g. after a DB wipe) keeps permanentId non-null
  // but resolvedPermanentId stays null, forcing the register path.
  const [resolvedPermanentId, setResolvedPermanentId] = useState<string | null>(null)

  useEffect(() => {
    if (!permanentId) return
    fetch(`/api/players/${permanentId}`)
      .then(r => {
        if (r.ok) return r.json()
        if (r.status === 404) {
          // Stale permanent_id — not in DB. Clear it so the register path runs.
          localStorage.removeItem(PERMANENT_ID_KEY)
        }
        return null
      })
      .then((data: { display_name: string } | null) => {
        if (data) {
          setName(data.display_name)
          setResolvedPermanentId(permanentId)
        }
      })
      .catch(() => {})
  }, [permanentId])

  async function handlePhotoChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setPhotoUploading(true)
    setError(null)
    try {
      const blob = await resizeImage(file)
      const preview = URL.createObjectURL(blob)
      setPhotoPreview(preview)

      const form = new FormData()
      form.append('file', blob, 'avatar.jpg')
      const res = await fetch('/api/photos/upload', { method: 'POST', body: form })
      if (!res.ok) {
        setError('Photo upload failed. Try again or skip.')
        setPhotoPreview(null)
        return
      }
      const { photo_url } = (await res.json()) as { photo_url: string }
      setPhotoUrl(photo_url)
      localStorage.setItem(PHOTO_URL_KEY, photo_url)
    } catch {
      setError('Could not process photo.')
      setPhotoPreview(null)
    } finally {
      setPhotoUploading(false)
      // Reset file input so the same file can be re-selected if needed
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  function handleClearPhoto() {
    setPhotoUrl(null)
    setPhotoPreview(null)
    localStorage.removeItem(PHOTO_URL_KEY)
  }

  const canJoin = name.trim().length > 0 && code.trim().length > 0

  async function handleJoin() {
    if (!canJoin || loading) return
    setLoading(true)
    setError(null)

    try {
      let pid = resolvedPermanentId

      if (!pid) {
        // First-time player (or stale ID was cleared): register their name
        const reg = await fetch('/api/players/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ display_name: name.trim() }),
        })
        if (!reg.ok) {
          setError('Could not register your name. Try again.')
          return
        }
        const regData = (await reg.json()) as { permanent_id: string }
        pid = regData.permanent_id
      } else {
        // Returning player may have edited their name — persist the change
        const putRes = await fetch(`/api/players/${pid}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ display_name: name.trim() }),
        })
        if (putRes.status === 404) {
          // ID became stale (e.g. DB rebuilt) — clear and re-register
          localStorage.removeItem(PERMANENT_ID_KEY)
          const reg = await fetch('/api/players/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ display_name: name.trim() }),
          })
          if (!reg.ok) {
            setError('Could not register your name. Try again.')
            return
          }
          const regData = (await reg.json()) as { permanent_id: string }
          pid = regData.permanent_id
        }
        // Other PUT errors (5xx, network) are non-fatal — proceed with existing ID
      }

      const res = await fetch(`/api/games/${code.trim()}/join`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ permanent_id: pid, avatar_id: avatarId, photo_url: photoUrl }),
      })

      if (res.status === 409) {
        setError('Game already started and you were not part of it.')
        return
      }

      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        setError((body as { detail?: string }).detail ?? 'Could not join. Check the code and try again.')
        return
      }

      const data = (await res.json()) as { game_id: string; player_id: string; session_token: string }
      onJoined({ game_id: data.game_id, player_id: data.player_id, session_token: data.session_token, permanent_id: pid! })
    } catch {
      setError('Network error. Is the server running?')
    } finally {
      setLoading(false)
    }
  }

  const displayPhoto = photoPreview ?? photoUrl

  return (
    <div className="onboarding create-match">
      {/* iOS in-app browser warning — QR camera opens a temporary context with
          isolated localStorage. Switching to Safari later loses the session.   */}
      {inAppBrowser && (
        <div className="onboarding__safari-banner">
          <span>⚠️ Open in Safari to keep your session if you switch apps.</span>
          <a
            className="onboarding__safari-link"
            href={window.location.href}
            target="_blank"
            rel="noreferrer"
          >
            Open in Safari
          </a>
        </div>
      )}

      {savedSession && onRejoin && (
        <div className="onboarding__rejoin">
          <span className="onboarding__rejoin-label">Game in progress: <strong>{savedSession.game_id}</strong></span>
          <button type="button" className="onboarding__rejoin-btn" onClick={onRejoin}>
            Rejoin
          </button>
        </div>
      )}

      <h1 className="onboarding__title">Werewolf</h1>

      {/* Name input — pre-filled and editable for returning players */}
      <div className="onboarding__field">
        <label htmlFor="player-name">Your name</label>
        <input
          id="player-name"
          type="text"
          autoFocus
          maxLength={16}
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="Enter your name"
          className="onboarding__input"
          onKeyDown={e => e.key === 'Enter' && handleJoin()}
        />
      </div>

      {/* Photo upload — replaces the color circle when a photo is set */}
      <div className="onboarding__field">
        <label>Your photo</label>
        <div className="onboarding__photo-row">
          {displayPhoto ? (
            <div className="onboarding__photo-preview-wrap">
              <img src={displayPhoto} alt="Your avatar" className="onboarding__photo-preview" />
              <button type="button" className="onboarding__photo-clear" onClick={handleClearPhoto} aria-label="Remove photo">✕</button>
            </div>
          ) : (
            <button
              type="button"
              className="onboarding__photo-btn"
              onClick={() => fileInputRef.current?.click()}
              disabled={photoUploading}
            >
              {photoUploading ? 'Uploading…' : '📷 Upload Photo'}
            </button>
          )}
          {displayPhoto && (
            <button
              type="button"
              className="onboarding__photo-change"
              onClick={() => fileInputRef.current?.click()}
              disabled={photoUploading}
            >
              Change
            </button>
          )}
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="onboarding__photo-input"
          onChange={handlePhotoChange}
        />
      </div>

      {/* Icon picker — hidden when a photo is set */}
      {!displayPhoto && (
        <div className="onboarding__field">
          <label>Choose your icon</label>
          <div className="onboarding__icon-row">
            {AVATAR_ICONS.map(id => (
              <button
                key={id}
                type="button"
                className={`onboarding__icon-btn${avatarId === id ? ' onboarding__icon-btn--selected' : ''}`}
                onClick={() => setAvatarId(id)}
                aria-label={id}
              >
                <img
                  src={`/images/${id}.png`}
                  alt={id}
                  className="onboarding__icon-img"
                  draggable={false}
                />
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Game code input */}
      <div className="onboarding__field">
        <label htmlFor="game-code">Game code</label>
        <input
          id="game-code"
          type="text"
          maxLength={4}
          value={code}
          onChange={e => setCode(e.target.value.toUpperCase())}
          placeholder="e.g. K7BX"
          className="onboarding__input onboarding__input--code"
          onKeyDown={e => e.key === 'Enter' && handleJoin()}
        />
      </div>

      {error && <p className="onboarding__error">{error}</p>}

      <button
        type="button"
        className="onboarding__cta btn-grad"
        disabled={!canJoin || loading || photoUploading}
        onClick={handleJoin}
      >
        {loading ? 'Joining…' : 'Join Game'}
      </button>

    </div>
  )
}
