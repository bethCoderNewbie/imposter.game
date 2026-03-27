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

export default function WolfVoteUI({ gameState, myPlayer, sendIntent }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { vibrate } = useHaptics()

  // Living non-wolf players as targets
  const targets = Object.values(gameState.players).filter(p =>
    p.is_alive && p.player_id !== myPlayer.player_id && p.team !== 'werewolf',
  )

  function handleConfirm() {
    if (!selectedId) return
    vibrate(300)
    sendIntent({ type: 'submit_night_action', target_id: selectedId })
  }

  return (
    <div className="action-ui">
      <p className="action-ui__header">Choose your target</p>

      <div className="action-ui__list">
        {targets.map(p => (
          <button
            key={p.player_id}
            className={`action-ui__row ${selectedId === p.player_id ? 'action-ui__row--selected action-ui__row--wolf' : ''}`}
            onClick={() => setSelectedId(p.player_id)}
          >
            <PlayerAvatar player={p} />
            <span>{p.display_name}</span>
          </button>
        ))}
      </div>

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
