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

type Mode = 'douse' | 'ignite'

export default function ArsonistUI({ gameState, myPlayer, sendIntent }: Props) {
  const [mode, setMode] = useState<Mode>('douse')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { vibrate } = useHaptics()

  const dousedCount = myPlayer.doused_player_ids?.length ?? 0

  const targets = Object.values(gameState.players).filter(
    p => p.is_alive && p.player_id !== myPlayer.player_id,
  )

  function handleConfirm() {
    vibrate(300)
    if (mode === 'douse') {
      if (!selectedId) return
      sendIntent({ type: 'submit_night_action', arsonist_action: 'douse', target_id: selectedId })
    } else {
      sendIntent({ type: 'submit_night_action', arsonist_action: 'ignite' })
    }
  }

  const canConfirm = mode === 'douse' ? selectedId !== null : dousedCount > 0

  return (
    <div className="action-ui">
      <div className="action-ui__mode-toggle">
        <button
          className={`action-ui__mode-btn ${mode === 'douse' ? 'action-ui__mode-btn--active' : ''}`}
          onClick={() => { setMode('douse'); setSelectedId(null) }}
        >
          Douse
        </button>
        <button
          className={`action-ui__mode-btn ${mode === 'ignite' ? 'action-ui__mode-btn--active' : ''}`}
          disabled={dousedCount === 0}
          onClick={() => setMode('ignite')}
        >
          Ignite {dousedCount > 0 ? `(${dousedCount})` : ''}
        </button>
      </div>

      {mode === 'douse' && (
        <>
          <p className="action-ui__header">Choose who to douse</p>
          <div className="action-ui__list">
            {targets.map(p => (
              <button
                key={p.player_id}
                className={`action-ui__row ${selectedId === p.player_id ? 'action-ui__row--selected' : ''}`}
                onClick={() => setSelectedId(p.player_id)}
              >
                <PlayerAvatar player={p} />
                <span>{p.display_name}</span>
                {myPlayer.doused_player_ids?.includes(p.player_id) && (
                  <span className="action-ui__tag">doused</span>
                )}
              </button>
            ))}
          </div>
        </>
      )}

      {mode === 'ignite' && (
        <p className="action-ui__header">
          Ignite {dousedCount} doused player{dousedCount !== 1 ? 's' : ''}
        </p>
      )}

      <button
        className="action-ui__confirm"
        disabled={!canConfirm}
        onClick={handleConfirm}
      >
        {mode === 'douse' ? 'Douse' : 'Ignite'}
      </button>
    </div>
  )
}
