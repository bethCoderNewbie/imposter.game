import { useState } from 'react'
import { useHaptics } from '../../hooks/useHaptics'
import PlayerAvatar from '../PlayerAvatar/PlayerAvatar'
import type { PlayerState, StrippedGameState } from '../../types/game'
import './ActionUI.css'

interface Props {
  gameState: StrippedGameState
  myPlayer: PlayerState
  sendIntent: (payload: Record<string, unknown>) => void
}

type Mode = 'heal' | 'kill'

export default function WitchUI({ gameState, myPlayer, sendIntent }: Props) {
  const [mode, setMode] = useState<Mode | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { vibrate } = useHaptics()

  const healUsed = myPlayer.witch_heal_used ?? false
  const killUsed = myPlayer.witch_kill_used ?? false

  if (healUsed && killUsed) {
    return <p className="action-ui__header">Both potions exhausted. Awaiting dawn…</p>
  }

  function handleConfirm() {
    if (!mode || !selectedId) return
    vibrate(300)
    sendIntent({ type: 'submit_night_action', witch_action: mode, target_id: selectedId })
  }

  function handleSkip() {
    vibrate(100)
    sendIntent({ type: 'submit_night_action', witch_action: 'skip' })
  }

  if (mode === null) {
    return (
      <div className="action-ui">
        <p className="action-ui__header">Choose your potion</p>
        <div className="action-ui__mode-toggle">
          <button
            className={`action-ui__mode-btn ${healUsed ? '' : 'action-ui__mode-btn--active'}`}
            disabled={healUsed}
            onClick={() => { setMode('heal'); setSelectedId(null) }}
          >
            Heal{healUsed ? ' (used)' : ''}
          </button>
          <button
            className={`action-ui__mode-btn ${killUsed ? '' : 'action-ui__mode-btn--active'}`}
            disabled={killUsed}
            onClick={() => { setMode('kill'); setSelectedId(null) }}
          >
            Kill{killUsed ? ' (used)' : ''}
          </button>
        </div>
        <button className="action-ui__confirm" onClick={handleSkip}>
          Do nothing tonight
        </button>
      </div>
    )
  }

  const targets = Object.values(gameState.players).filter(
    p => p.is_alive && (mode === 'heal' || p.player_id !== myPlayer.player_id),
  )

  return (
    <div className="action-ui">
      <p className="action-ui__header">
        {mode === 'heal' ? 'Who to protect tonight?' : 'Who to curse?'}
      </p>

      <div className="action-ui__list">
        {targets.map(p => (
          <button
            key={p.player_id}
            className={`action-ui__row ${selectedId === p.player_id ? 'action-ui__row--selected' : ''}`}
            onClick={() => setSelectedId(p.player_id)}
          >
            <PlayerAvatar player={p} />
            <span>{p.display_name}{p.player_id === myPlayer.player_id ? ' (you)' : ''}</span>
          </button>
        ))}
      </div>

      <button
        className="action-ui__confirm"
        onClick={() => { setMode(null); setSelectedId(null) }}
      >
        Back
      </button>

      <button
        className="action-ui__confirm"
        disabled={!selectedId}
        onClick={handleConfirm}
      >
        Confirm
      </button>
    </div>
  )
}
