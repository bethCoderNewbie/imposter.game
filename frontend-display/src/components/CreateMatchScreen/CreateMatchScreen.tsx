import { useState } from 'react'
import type { DifficultyLevel } from '../../types/game'
import {
  DIFFICULTY_LABELS,
  TIMER_LABELS,
  TIMER_STEPS,
  TIMER_MIN,
  TIMER_FIELDS,
  DEFAULT_CONFIG,
} from '../LobbyConfigPanel/config'
import './CreateMatchScreen.css'

interface Props {
  onCreated: (gameId: string, hostSecret: string) => void
  onResumed: (gameId: string) => void
}

export default function CreateMatchScreen({ onCreated, onResumed }: Props) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showResume, setShowResume] = useState(false)
  const [resumeId, setResumeId] = useState('')
  const [resumeError, setResumeError] = useState<string | null>(null)

  // Pre-game settings (applied via PATCH immediately after game creation)
  const [difficulty, setDifficulty] = useState<DifficultyLevel>(DEFAULT_CONFIG.difficulty_level)
  const [nightTimer, setNightTimer] = useState(DEFAULT_CONFIG.night_timer_seconds)
  const [dayTimer, setDayTimer] = useState(DEFAULT_CONFIG.day_timer_seconds)
  const [voteTimer, setVoteTimer] = useState(DEFAULT_CONFIG.vote_timer_seconds)

  const [draftTimers, setDraftTimers] = useState<Record<string, string>>({
    night_timer_seconds: String(DEFAULT_CONFIG.night_timer_seconds),
    day_timer_seconds:   String(DEFAULT_CONFIG.day_timer_seconds),
    vote_timer_seconds:  String(DEFAULT_CONFIG.vote_timer_seconds),
  })

  const timerValues: Record<string, number> = {
    night_timer_seconds: nightTimer,
    day_timer_seconds: dayTimer,
    vote_timer_seconds: voteTimer,
  }

  const timerSetters: Record<string, (v: number) => void> = {
    night_timer_seconds: setNightTimer,
    day_timer_seconds: setDayTimer,
    vote_timer_seconds: setVoteTimer,
  }

  function adjustTimer(field: string, delta: number) {
    const lo = TIMER_MIN[field]
    const next = timerValues[field] + delta
    if (next >= lo) {
      timerSetters[field](next)
      setDraftTimers(d => ({ ...d, [field]: String(next) }))
    }
  }

  function commitTimer(field: string, raw: string) {
    const lo = TIMER_MIN[field]
    const parsed = parseInt(raw, 10)
    if (isNaN(parsed) || parsed < lo) {
      setDraftTimers(d => ({ ...d, [field]: String(timerValues[field]) }))
      return
    }
    timerSetters[field](parsed)
    setDraftTimers(d => ({ ...d, [field]: String(parsed) }))
  }

  async function handleCreate() {
    if (loading) return
    setLoading(true)
    setError(null)

    try {
      const res = await fetch('/api/games', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        setError((body as { detail?: string }).detail ?? 'Could not create game. Try again.')
        return
      }
      const data = (await res.json()) as { game_id: string; host_secret: string }
      const { game_id, host_secret } = data

      // Apply pre-game settings before signalling the parent
      await fetch(`/api/games/${game_id}/config`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          host_secret,
          difficulty_level: difficulty,
          night_timer_seconds: nightTimer,
          day_timer_seconds: dayTimer,
          vote_timer_seconds: voteTimer,
        }),
      })

      onCreated(game_id, host_secret)
    } catch {
      setError('Network error. Is the server running?')
    } finally {
      setLoading(false)
    }
  }

  function handleResume() {
    if (!resumeId.trim()) {
      setResumeError('Please enter a game ID.')
      return
    }
    setResumeError(null)
    onResumed(resumeId.trim())
  }

  return (
    <div className="create-match">
      <div className="create-match__content">
        <h1 className="create-match__title">🐺 Werewolf</h1>
        <p className="create-match__sub">Social deduction for 5–18 players</p>

        {/* Pre-game settings */}
        <div className="create-match__settings">
          <div className="create-match__settings-section">
            <span className="create-match__settings-label">DIFFICULTY</span>
            <div className="create-match__difficulty-group">
              {(['easy', 'standard', 'hard'] as DifficultyLevel[]).map(level => (
                <button
                  key={level}
                  className={`create-match__difficulty-btn${difficulty === level ? ' create-match__difficulty-btn--active' : ''}`}
                  onClick={() => setDifficulty(level)}
                >
                  {DIFFICULTY_LABELS[level]}
                </button>
              ))}
            </div>
          </div>

          <div className="create-match__settings-section">
            <span className="create-match__settings-label">PHASE TIMERS</span>
            {TIMER_FIELDS.map(field => {
              const value = timerValues[field]
              const step = TIMER_STEPS[field]
              const lo = TIMER_MIN[field]
              return (
                <div key={field} className="create-match__timer-row">
                  <span className="create-match__timer-label">{TIMER_LABELS[field]}</span>
                  <button
                    className="create-match__stepper"
                    disabled={value <= lo}
                    onClick={() => adjustTimer(field, -step)}
                  >−</button>
                  <input
                    type="number"
                    className="create-match__timer-input"
                    value={draftTimers[field]}
                    min={lo}
                    onChange={e => setDraftTimers(d => ({ ...d, [field]: e.target.value }))}
                    onBlur={e => commitTimer(field, e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') commitTimer(field, (e.target as HTMLInputElement).value) }}
                  />
                  <button
                    className="create-match__stepper"
                    onClick={() => adjustTimer(field, step)}
                  >+</button>
                </div>
              )
            })}
          </div>
        </div>

        {error && <p className="create-match__error">{error}</p>}

        <button
          className="create-match__btn btn-grad"
          disabled={loading}
          onClick={handleCreate}
        >
          {loading ? 'Creating…' : 'Create New Match'}
        </button>

        <button
          className="create-match__btn btn-grad"
          onClick={() => { setShowResume(v => !v); setResumeError(null) }}
        >
          {showResume ? 'Cancel' : 'Resume Match'}
        </button>

        {showResume && (
          <div className="create-match__resume">
            {resumeError && <p className="create-match__error">{resumeError}</p>}
            <input
              className="create-match__resume-input"
              type="text"
              placeholder="Game ID"
              value={resumeId}
              onChange={e => setResumeId(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleResume() }}
            />
            <button
              className="create-match__btn btn-grad"
              disabled={!resumeId.trim()}
              onClick={handleResume}
            >
              Resume
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
