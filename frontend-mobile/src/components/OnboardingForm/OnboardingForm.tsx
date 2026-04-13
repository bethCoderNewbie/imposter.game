import { useState } from 'react'
import { AVATAR_COLORS } from '../../types/game'
import './OnboardingForm.css'

interface JoinedSession {
  game_id: string
  player_id: string
  session_token: string
}

interface Props {
  prefillCode: string
  onJoined: (session: JoinedSession) => void
}

const AVATAR_IDS = Object.keys(AVATAR_COLORS) // avatar_01 … avatar_08

const SESSION_KEY = 'ww_session'

function loadStoredSession(): { game_id: string; session_token: string } | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as { game_id?: string; session_token?: string }
    if (parsed.game_id && parsed.session_token) return parsed as { game_id: string; session_token: string }
    return null
  } catch { return null }
}

export default function OnboardingForm({ prefillCode, onJoined }: Props) {
  // ── Join mode ────────────────────────────────────────────────────────────────
  const [name, setName] = useState('')
  const [code, setCode] = useState(prefillCode.toUpperCase())
  const [avatarId, setAvatarId] = useState('avatar_01')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // ── Rejoin mode ──────────────────────────────────────────────────────────────
  const [mode, setMode] = useState<'join' | 'rejoin'>('join')
  const [rejoinCode, setRejoinCode] = useState(prefillCode.toUpperCase())
  const [rejoinToken, setRejoinToken] = useState('')
  const [rejoinLoading, setRejoinLoading] = useState(false)
  const [rejoinError, setRejoinError] = useState<string | null>(null)

  const canJoin = name.trim().length > 0 && code.trim().length > 0
  const canRejoin = rejoinCode.trim().length > 0 && rejoinToken.trim().length > 0

  // ── Shared rejoin call ───────────────────────────────────────────────────────
  async function attemptRejoin(gameCode: string, token: string): Promise<boolean> {
    const res = await fetch(`/api/games/${gameCode.trim()}/rejoin`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_token: token.trim() }),
    })
    if (!res.ok) return false
    const data = (await res.json()) as { game_id: string; player_id: string; session_token: string }
    onJoined({ game_id: data.game_id, player_id: data.player_id, session_token: data.session_token })
    return true
  }

  // ── Join handler ─────────────────────────────────────────────────────────────
  async function handleJoin() {
    if (!canJoin || loading) return
    setLoading(true)
    setError(null)

    try {
      const res = await fetch(`/api/games/${code.trim()}/join`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: name.trim(), avatar_id: avatarId }),
      })

      if (res.status === 409) {
        // Game already started — try stored session silently, then surface rejoin UI
        const stored = loadStoredSession()
        if (stored && stored.game_id.toUpperCase() === code.trim()) {
          const ok = await attemptRejoin(code, stored.session_token)
          if (ok) return
        }
        // Switch to rejoin mode with the code pre-filled
        setRejoinCode(code)
        setRejoinError('Game already started. Paste your session token to rejoin.')
        setMode('rejoin')
        return
      }

      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        setError((body as { detail?: string }).detail ?? 'Could not join. Check the code and try again.')
        return
      }

      const data = (await res.json()) as { game_id: string; player_id: string; session_token: string }
      onJoined({ game_id: data.game_id, player_id: data.player_id, session_token: data.session_token })
    } catch {
      setError('Network error. Is the server running?')
    } finally {
      setLoading(false)
    }
  }

  // ── Rejoin handler ───────────────────────────────────────────────────────────
  async function handleRejoin() {
    if (!canRejoin || rejoinLoading) return
    setRejoinLoading(true)
    setRejoinError(null)
    try {
      const ok = await attemptRejoin(rejoinCode, rejoinToken)
      if (!ok) setRejoinError('Invalid session token or game not found.')
    } catch {
      setRejoinError('Network error. Is the server running?')
    } finally {
      setRejoinLoading(false)
    }
  }

  // ── Rejoin mode UI ───────────────────────────────────────────────────────────
  if (mode === 'rejoin') {
    return (
      <div className="onboarding">
        <h1 className="onboarding__title">Werewolf</h1>
        <p className="onboarding__sub">Returning to a game in progress</p>

        <div className="onboarding__field">
          <label htmlFor="rejoin-code">Game code</label>
          <input
            id="rejoin-code"
            type="text"
            maxLength={8}
            value={rejoinCode}
            onChange={e => setRejoinCode(e.target.value.toUpperCase())}
            placeholder="e.g. ABC123"
            className="onboarding__input onboarding__input--code"
          />
        </div>

        <div className="onboarding__field">
          <label htmlFor="rejoin-token">Session token</label>
          <textarea
            id="rejoin-token"
            value={rejoinToken}
            onChange={e => setRejoinToken(e.target.value.trim())}
            placeholder="Paste your session token here"
            className="onboarding__input onboarding__input--token"
            rows={3}
          />
        </div>

        {rejoinError && <p className="onboarding__error">{rejoinError}</p>}

        <button
          type="button"
          className="onboarding__cta"
          disabled={!canRejoin || rejoinLoading}
          onClick={handleRejoin}
        >
          {rejoinLoading ? 'Rejoining…' : 'Rejoin Game'}
        </button>

        <button
          type="button"
          className="onboarding__link"
          onClick={() => { setMode('join'); setError(null) }}
        >
          Join a new game instead
        </button>
      </div>
    )
  }

  // ── Join mode UI ─────────────────────────────────────────────────────────────
  return (
    <div className="onboarding">
      <h1 className="onboarding__title">Werewolf</h1>

      {/* Name input */}
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

      {/* Avatar picker — 8 preset color circles */}
      <div className="onboarding__field">
        <label>Choose your color</label>
        <div className="onboarding__avatars">
          {AVATAR_IDS.map(id => (
            <button
              key={id}
              type="button"
              className={`onboarding__avatar-btn ${avatarId === id ? 'onboarding__avatar-btn--selected' : ''}`}
              style={{ backgroundColor: AVATAR_COLORS[id] }}
              onClick={() => setAvatarId(id)}
              aria-label={id}
            />
          ))}
        </div>
      </div>

      {/* Game code input */}
      <div className="onboarding__field">
        <label htmlFor="game-code">Game code</label>
        <input
          id="game-code"
          type="text"
          maxLength={8}
          value={code}
          onChange={e => setCode(e.target.value.toUpperCase())}
          placeholder="e.g. ABC123"
          className="onboarding__input onboarding__input--code"
          onKeyDown={e => e.key === 'Enter' && handleJoin()}
        />
      </div>

      {error && <p className="onboarding__error">{error}</p>}

      <button
        type="button"
        className="onboarding__cta"
        disabled={!canJoin || loading}
        onClick={handleJoin}
      >
        {loading ? 'Joining…' : 'Join Game'}
      </button>

      <button
        type="button"
        className="onboarding__link"
        onClick={() => { setRejoinCode(code); setRejoinError(null); setMode('rejoin') }}
      >
        Returning player? Rejoin here
      </button>
    </div>
  )
}
