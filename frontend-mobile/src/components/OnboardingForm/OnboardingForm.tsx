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

export default function OnboardingForm({ prefillCode, onJoined }: Props) {
  const [name, setName] = useState('')
  const [code, setCode] = useState(prefillCode.toUpperCase())
  const [avatarId, setAvatarId] = useState('avatar_01')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const canJoin = name.trim().length > 0 && code.trim().length > 0

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
    </div>
  )
}
