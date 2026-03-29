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

export default function CupidUI({ gameState, myPlayer, sendIntent }: Props) {
  const [targetA, setTargetA] = useState<string | null>(null)
  const [targetB, setTargetB] = useState<string | null>(null)
  const { vibrate } = useHaptics()

  const allPlayers = Object.values(gameState.players).filter(
    p => p.is_alive && p.player_id !== myPlayer.player_id,
  )

  // Step 1: pick first lover; step 2: pick second (cannot re-pick first)
  const pickingB = targetA !== null && targetB === null

  function handleSelect(playerId: string) {
    if (!targetA) {
      setTargetA(playerId)
    } else if (playerId !== targetA) {
      setTargetB(playerId)
    }
  }

  function handleConfirm() {
    if (!targetA || !targetB) return
    vibrate(300)
    sendIntent({ type: 'submit_night_action', link_target_a: targetA, link_target_b: targetB })
  }

  function handleReset() {
    setTargetA(null)
    setTargetB(null)
  }

  const nameA = targetA ? allPlayers.find(p => p.player_id === targetA)?.display_name : null
  const nameB = targetB ? allPlayers.find(p => p.player_id === targetB)?.display_name : null

  return (
    <div className="action-ui">
      <p className="action-ui__header">
        {!targetA ? 'Choose the first lover' : !targetB ? 'Choose the second lover' : 'Confirm the pair'}
      </p>

      {(targetA || targetB) && (
        <div className="action-ui__cupid-selection">
          <span className="action-ui__cupid-pair">
            {nameA ?? '?'} ♥ {nameB ?? '?'}
          </span>
          {!targetB && (
            <button className="action-ui__tag" onClick={handleReset}>Reset</button>
          )}
        </div>
      )}

      {!targetB && (
        <div className="action-ui__list">
          {allPlayers.map(p => {
            const isChosen = p.player_id === targetA
            const isDisabled = pickingB && isChosen
            return (
              <button
                key={p.player_id}
                className={`action-ui__row ${isChosen ? 'action-ui__row--selected' : ''} ${isDisabled ? 'action-ui__row--disabled' : ''}`}
                disabled={isDisabled}
                onClick={() => handleSelect(p.player_id)}
              >
                <PlayerAvatar player={p} />
                <span>{p.display_name}</span>
              </button>
            )
          })}
        </div>
      )}

      {targetA && targetB && (
        <button
          className="action-ui__confirm"
          onClick={handleConfirm}
        >
          Link them
        </button>
      )}
    </div>
  )
}
