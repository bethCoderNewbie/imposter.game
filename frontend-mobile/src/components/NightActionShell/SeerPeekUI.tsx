import { useState, useEffect } from 'react'
import { useHaptics } from '../../hooks/useHaptics'
import PlayerAvatar from '../PlayerAvatar/PlayerAvatar'
import type { PlayerState, StrippedGameState, InvestigationResult } from '../../types/game'
import './ActionUI.css'

interface Props {
  gameState: StrippedGameState
  myPlayer: PlayerState
  sendIntent: (payload: Record<string, unknown>) => void
}

interface PeekRecord {
  round: number
  target_name: string
  result: InvestigationResult
}

/** ADR-003 §9 — Seer peek history in sessionStorage.
 *  Server is authoritative; sessionStorage is a display cache re-hydrated on mount. */
function historyKey(gameId: string, playerId: string) {
  return `ww_seer_${gameId}_${playerId}`
}

export default function SeerPeekUI({ gameState, myPlayer, sendIntent }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [history, setHistory] = useState<PeekRecord[]>([])
  const { vibrate } = useHaptics()
  const submitted = myPlayer.night_action_submitted

  // Load history from sessionStorage on mount
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(historyKey(gameState.game_id, myPlayer.player_id))
      if (raw) setHistory(JSON.parse(raw) as PeekRecord[])
    } catch { /* ignore */ }
  }, [])

  // Detect new seer_result broadcast and append to history
  useEffect(() => {
    const result = gameState.night_actions.seer_result
    const targetId = gameState.night_actions.seer_target_id
    if (!result || !targetId) return
    const targetPlayer = gameState.players[targetId]
    if (!targetPlayer) return

    const record: PeekRecord = {
      round: gameState.round,
      target_name: targetPlayer.display_name,
      result,
    }
    setHistory(prev => {
      const alreadyHave = prev.some(r => r.round === record.round && r.target_name === record.target_name)
      if (alreadyHave) return prev
      const next = [...prev, record]
      sessionStorage.setItem(historyKey(gameState.game_id, myPlayer.player_id), JSON.stringify(next))
      return next
    })
  }, [gameState.night_actions.seer_result]) // eslint-disable-line react-hooks/exhaustive-deps

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
        {submitted ? 'Waiting for others…' : 'Choose who to investigate'}
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

      {/* Current round result — rendered once server broadcasts resolve */}
      {gameState.night_actions.seer_result && (
        <p className={`action-ui__result action-ui__result--${gameState.night_actions.seer_result}`}>
          {gameState.players[gameState.night_actions.seer_target_id ?? '']?.display_name} is…{' '}
          {gameState.night_actions.seer_result === 'wolf' ? 'a WOLF' : 'NOT a Wolf'}
        </p>
      )}

      {/* Peek history */}
      {history.length > 0 && (
        <div className="action-ui__history">
          <p className="action-ui__history-label">Previous peeks</p>
          {history.map((h, i) => (
            <p key={i} className={`action-ui__history-row action-ui__result--${h.result}`}>
              Round {h.round}: {h.target_name} — {h.result === 'wolf' ? 'WOLF' : 'Not Wolf'}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}
