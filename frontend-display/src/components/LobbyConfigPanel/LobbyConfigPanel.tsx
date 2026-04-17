import { useState, useEffect } from 'react'
import type { GameConfig, DifficultyLevel } from '../../types/game'
import { getApiBase } from '../../utils/backend'
import {
  formatSeconds,
  DIFFICULTY_LABELS,
  TIMER_STEPS,
  TIMER_MIN,
  TIMER_LABELS,
  voiceLabel,
} from './config'
import './LobbyConfigPanel.css'

interface Props {
  config: GameConfig
  hostSecret?: string
  gameId?: string
}

export default function LobbyConfigPanel({ config, hostSecret, gameId }: Props) {
  const [isPatching, setIsPatching] = useState(false)
  const [voices, setVoices] = useState<string[]>([])
  const [draftTimers, setDraftTimers] = useState<Record<string, string>>({
    night_timer_seconds: String(config.night_timer_seconds),
    day_timer_seconds:   String(config.day_timer_seconds),
    vote_timer_seconds:  String(config.vote_timer_seconds),
  })

  useEffect(() => {
    setDraftTimers({
      night_timer_seconds: String(config.night_timer_seconds),
      day_timer_seconds:   String(config.day_timer_seconds),
      vote_timer_seconds:  String(config.vote_timer_seconds),
    })
  }, [config.night_timer_seconds, config.day_timer_seconds, config.vote_timer_seconds])

  useEffect(() => {
    fetch(`${getApiBase()}/api/narrator/voices`)
      .then(r => r.json())
      .then(data => setVoices(data.voices ?? []))
      .catch(() => {})
  }, [])

  async function patch(updates: Record<string, unknown>) {
    if (!gameId || !hostSecret || isPatching) return
    setIsPatching(true)
    try {
      await fetch(`${getApiBase()}/api/games/${gameId}/config`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host_secret: hostSecret, ...updates }),
      })
    } finally {
      setIsPatching(false)
    }
  }

  function commitTimer(field: string, raw: string) {
    const lo = TIMER_MIN[field]
    const parsed = parseInt(raw, 10)
    if (isNaN(parsed) || parsed < lo) {
      setDraftTimers(d => ({ ...d, [field]: String((config as unknown as Record<string, unknown>)[field]) }))
      return
    }
    patch({ [field]: parsed })
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
        <span className="lobby-config-panel__timer-summary">
          {voiceLabel(config.narrator_voice)}
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
          const lo = TIMER_MIN[field]
          return (
            <div key={field} className="lobby-config-panel__timer-row">
              <span className="lobby-config-panel__timer-label">{TIMER_LABELS[field]}</span>
              <button
                className="lobby-config-panel__stepper"
                disabled={isPatching || value <= lo}
                onClick={() => patch({ [field]: value - step })}
              >−</button>
              <input
                type="number"
                className="lobby-config-panel__timer-input"
                value={draftTimers[field]}
                min={lo}
                disabled={isPatching}
                onChange={e => setDraftTimers(d => ({ ...d, [field]: e.target.value }))}
                onBlur={e => commitTimer(field, e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') commitTimer(field, (e.target as HTMLInputElement).value) }}
              />
              <button
                className="lobby-config-panel__stepper"
                disabled={isPatching}
                onClick={() => patch({ [field]: value + step })}
              >+</button>
            </div>
          )
        })}
      </div>

      {voices.length > 0 && (
        <div className="lobby-config-panel__section">
          <span className="lobby-config-panel__label">NARRATOR</span>
          <div className="lobby-config-panel__difficulty-group">
            {voices.map(v => (
              <button
                key={v}
                className={`lobby-config-panel__difficulty-btn${config.narrator_voice === v ? ' lobby-config-panel__difficulty-btn--active' : ''}`}
                disabled={isPatching}
                onClick={() => patch({ narrator_voice: v })}
              >
                {voiceLabel(v)}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
