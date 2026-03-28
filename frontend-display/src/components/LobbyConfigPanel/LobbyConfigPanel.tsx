import { useState } from 'react'
import type { GameConfig, DifficultyLevel } from '../../types/game'
import './LobbyConfigPanel.css'

interface Props {
  config: GameConfig
  hostSecret?: string
  gameId?: string
}

function formatSeconds(s: number): string {
  const m = Math.floor(s / 60)
  const rem = s % 60
  return m > 0 ? `${m}:${String(rem).padStart(2, '0')}` : `${s}s`
}

const DIFFICULTY_LABELS: Record<DifficultyLevel, string> = {
  easy: 'Easy', standard: 'Balanced', hard: 'Hard',
}

const TIMER_STEPS: Record<string, number> = {
  night_timer_seconds: 15,
  day_timer_seconds: 30,
  vote_timer_seconds: 15,
}

const TIMER_BOUNDS: Record<string, [number, number]> = {
  night_timer_seconds:  [30,  120],
  day_timer_seconds:    [60,  300],
  vote_timer_seconds:   [30,  120],
}

const TIMER_LABELS: Record<string, string> = {
  night_timer_seconds: 'Night',
  day_timer_seconds:   'Day',
  vote_timer_seconds:  'Vote',
}

export default function LobbyConfigPanel({ config, hostSecret, gameId }: Props) {
  const [isPatching, setIsPatching] = useState(false)

  async function patch(updates: Record<string, unknown>) {
    if (!gameId || !hostSecret || isPatching) return
    setIsPatching(true)
    try {
      await fetch(`/api/games/${gameId}/config`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host_secret: hostSecret, ...updates }),
      })
    } finally {
      setIsPatching(false)
    }
  }

  const isHost = Boolean(hostSecret)

  if (!isHost) {
    return (
      <div className="lobby-config-panel lobby-config-panel--readonly">
        <span className="lobby-config-panel__difficulty-badge">
          {DIFFICULTY_LABELS[config.difficulty_level]}
        </span>
        <span className="lobby-config-panel__timer-summary">
          Night {formatSeconds(config.night_timer_seconds)}
          {' · '}Day {formatSeconds(config.day_timer_seconds)}
          {' · '}Vote {formatSeconds(config.vote_timer_seconds)}
        </span>
      </div>
    )
  }

  return (
    <div className="lobby-config-panel">
      <div className="lobby-config-panel__section">
        <span className="lobby-config-panel__label">DIFFICULTY</span>
        <div className="lobby-config-panel__difficulty-group">
          {(['easy', 'standard', 'hard'] as DifficultyLevel[]).map(level => (
            <button
              key={level}
              className={`lobby-config-panel__difficulty-btn${config.difficulty_level === level ? ' lobby-config-panel__difficulty-btn--active' : ''}`}
              disabled={isPatching}
              onClick={() => patch({ difficulty_level: level })}
            >
              {DIFFICULTY_LABELS[level]}
            </button>
          ))}
        </div>
      </div>

      <div className="lobby-config-panel__section">
        <span className="lobby-config-panel__label">PHASE TIMERS</span>
        {(['night_timer_seconds', 'day_timer_seconds', 'vote_timer_seconds'] as const).map(field => {
          const value = config[field]
          const step = TIMER_STEPS[field]
          const [lo, hi] = TIMER_BOUNDS[field]
          return (
            <div key={field} className="lobby-config-panel__timer-row">
              <span className="lobby-config-panel__timer-label">{TIMER_LABELS[field]}</span>
              <button
                className="lobby-config-panel__stepper"
                disabled={isPatching || value <= lo}
                onClick={() => patch({ [field]: value - step })}
              >−</button>
              <span className="lobby-config-panel__timer-value">{formatSeconds(value)}</span>
              <button
                className="lobby-config-panel__stepper"
                disabled={isPatching || value >= hi}
                onClick={() => patch({ [field]: value + step })}
              >+</button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
