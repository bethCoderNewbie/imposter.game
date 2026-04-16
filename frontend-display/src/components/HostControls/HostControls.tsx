import './HostControls.css'
import type { StrippedGameState } from '../../types/game'

interface Props {
  gameState: StrippedGameState
  sendIntent: (payload: Record<string, unknown>) => void
}

const ACTIVE_PHASES = ['night', 'role_deal', 'day', 'day_vote', 'hunter_pending']

export default function HostControls({ gameState, sendIntent }: Props) {
  if (!ACTIVE_PHASES.includes(gameState.phase)) return null

  const paused = gameState.timer_paused ?? false

  function send(type: string) {
    sendIntent({ type, player_id: gameState.host_player_id })
  }

  return (
    <div className="host-controls">
      <button
        className="host-controls__btn"
        onClick={() => send(paused ? 'resume_timer' : 'pause_timer')}
      >
        {paused ? '▶ Resume' : '⏸ Pause'}
      </button>
      <button className="host-controls__btn" onClick={() => send('extend_timer')}>
        +30s
      </button>
      {gameState.phase !== 'day' && (
        <button
          className="host-controls__btn host-controls__btn--skip"
          onClick={() => send('force_next')}
        >
          Skip ▶▶
        </button>
      )}
    </div>
  )
}
