import PlayerAvatar from '../PlayerAvatar/PlayerAvatar'
import type { StrippedGameState } from '../../types/game'
import './DeadSpectatorScreen.css'

interface Props {
  gameState: StrippedGameState
  myPlayerId: string
}

/** PRD-002 §3.6 — Dead spectator view.
 *  All action buttons removed from DOM (not disabled).
 *  Full role reveal for all living players — dead view receives roles from server. */
export default function DeadSpectatorScreen({ gameState, myPlayerId }: Props) {
  const players = Object.values(gameState.players)
  const living = players.filter(p => p.is_alive)
  const eliminated = players.filter(p => !p.is_alive)

  return (
    <div className="dead-spectator">
      <div className="dead-spectator__banner">You have been eliminated.</div>

      <div className="dead-spectator__section">
        <p className="dead-spectator__section-label">Still in the game</p>
        {living.map(p => (
          <div key={p.player_id} className="dead-spectator__row">
            <PlayerAvatar player={p} size={36} />
            <span className="dead-spectator__name">{p.display_name}</span>
            {p.role && (
              <span className="dead-spectator__role">{p.role}</span>
            )}
          </div>
        ))}
      </div>

      {eliminated.length > 0 && (
        <div className="dead-spectator__section">
          <p className="dead-spectator__section-label">Eliminated</p>
          {eliminated.map(p => (
            <div key={p.player_id} className={`dead-spectator__row dead-spectator__row--dead ${p.player_id === myPlayerId ? 'dead-spectator__row--me' : ''}`}>
              <PlayerAvatar player={p} size={36} style={{ filter: 'grayscale(1)' }} />
              <span className="dead-spectator__name">{p.display_name}</span>
              {p.role && (
                <span className="dead-spectator__role dead-spectator__role--muted">{p.role}</span>
              )}
            </div>
          ))}
        </div>
      )}

      <p className="dead-spectator__footer">Watch the game unfold…</p>
    </div>
  )
}
