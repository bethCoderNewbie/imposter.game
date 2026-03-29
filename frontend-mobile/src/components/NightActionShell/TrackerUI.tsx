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

export default function TrackerUI({ gameState, myPlayer, sendIntent }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { vibrate } = useHaptics()
  const submitted = myPlayer.night_action_submitted
  const trackerResult: string[] = gameState.night_actions.tracker_result ?? []

  const targets = Object.values(gameState.players).filter(
    p => p.is_alive && p.player_id !== myPlayer.player_id,
  )

  function handleConfirm() {
    if (!selectedId) return
    vibrate(300)
    sendIntent({ type: 'submit_night_action', target_id: selectedId })
  }

  return (
    <div className="action-ui">
      <p className="action-ui__header">
        {submitted ? 'Waiting for others…' : 'Choose who to follow'}
      </p>

      {!submitted && (
        <div className="action-ui__list">
          {targets.map(p => (
            <button
              key={p.player_id}
              className={`action-ui__row ${selectedId === p.player_id ? 'action-ui__row--selected' : ''}`}
              onClick={() => setSelectedId(p.player_id)}
            >
              <PlayerAvatar player={p} />
              <span>{p.display_name}</span>
            </button>
          ))}
        </div>
      )}

      {!submitted && (
        <button
          className="action-ui__confirm"
          disabled={!selectedId}
          onClick={handleConfirm}
        >
          Confirm
        </button>
      )}

      {/* Tracker result — rendered once server broadcasts resolve with non-empty visits */}
      {submitted && trackerResult.length > 0 && (
        <p className="action-ui__result">
          They visited:{' '}
          {trackerResult
            .map(pid => gameState.players[pid]?.display_name ?? pid)
            .join(', ')}
        </p>
      )}
    </div>
  )
}
