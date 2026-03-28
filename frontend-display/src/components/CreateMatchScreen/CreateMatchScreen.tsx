import { useState } from 'react'
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
      onCreated(data.game_id, data.host_secret)
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

        {error && <p className="create-match__error">{error}</p>}

        <button
          className="create-match__btn"
          disabled={loading}
          onClick={handleCreate}
        >
          {loading ? 'Creating…' : 'Create New Match'}
        </button>

        <button
          className="create-match__btn"
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
              className="create-match__btn"
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
