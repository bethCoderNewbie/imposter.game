import PlayerAvatar from '../PlayerAvatar/PlayerAvatar'
import type { StrippedGameState, PlayerRosterEntry } from '../../types/game'
import './LobbyWaitingScreen.css'

interface Props {
  gameState: StrippedGameState
  roster: PlayerRosterEntry[]
  myPlayerId: string
  sendIntent: (payload: Record<string, unknown>) => void
  onLeave: () => void
}

export default function LobbyWaitingScreen({ gameState, roster, myPlayerId, sendIntent, onLeave }: Props) {
  const players = roster.filter(p => p.is_connected)
  const isHost = gameState.host_player_id === myPlayerId
  const canStart = players.length >= 5

  function handleStart() {
    sendIntent({ type: 'start_game' })
  }

  return (
    <div className="lobby-waiting">
      <div className="lobby-waiting__header">
        <h2 className="lobby-waiting__code">{gameState.game_id}</h2>
        <p className="lobby-waiting__sub">{players.length} player{players.length !== 1 ? 's' : ''} joined</p>
      </div>

      <div className="lobby-waiting__list">
        {players.map(p => (
          <div key={p.player_id} className="lobby-waiting__player">
            <PlayerAvatar player={p} />
            <span className="lobby-waiting__name">
              {p.display_name}
              {p.player_id === myPlayerId && <span className="lobby-waiting__you"> (you)</span>}
              {p.player_id === gameState.host_player_id && <span className="lobby-waiting__host"> ★</span>}
            </span>
            <span className={`lobby-waiting__dot ${p.is_connected ? 'lobby-waiting__dot--on' : ''}`} />
          </div>
        ))}
      </div>

      {isHost && (
        <div className="lobby-waiting__start-area">
          <button
            className="lobby-waiting__start-btn"
            disabled={!canStart}
            onClick={handleStart}
          >
            {canStart ? 'Start Game' : `Need ${5 - players.length} more player${5 - players.length !== 1 ? 's' : ''}`}
          </button>
        </div>
      )}

      {!isHost && (
        <p className="lobby-waiting__waiting">Waiting for host to start…</p>
      )}

      <button className="lobby-waiting__leave-btn" onClick={onLeave}>
        Leave lobby
      </button>
    </div>
  )
}
