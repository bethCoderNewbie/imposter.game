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

export default function BodyguardUI({ gameState, myPlayer, sendIntent }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { vibrate } = useHaptics()

  const targets = Object.values(gameState.players).filter(p => p.is_alive)

  function handleConfirm() {
    if (!selectedId) return
    vibrate(300)
    sendIntent({ type: 'submit_night_action', target_id: selectedId })
  }

  return (
    <div className="action-ui">
      <p className="action-ui__header">Choose who to guard tonight</p>

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
        disabled={!selectedId}
        onClick={handleConfirm}
      >
        Guard
      </button>
    </div>
  )
}
