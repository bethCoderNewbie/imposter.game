import PlayerAvatar from '../PlayerAvatar/PlayerAvatar'
import type { StrippedGameState } from '../../types/game'
import './GameOverScreen.css'

interface Props {
  gameState: StrippedGameState
  myPlayerId: string
}

const CAUSE_LABELS: Record<string, string> = {
  wolf_kill:        'Killed by wolves',
  village_vote:     'Voted out',
  arsonist_ignite:  'Burned alive',
  serial_killer_kill: 'Serial killer',
  broken_heart:     'Died of broken heart',
  hunter_revenge:   'Hunter revenge',
}

function winnerHeading(gameState: StrippedGameState): string {
  if (gameState.winner === 'village') return 'Village Wins!'
  if (gameState.winner === 'werewolf') return 'Wolves Win!'
  if (gameState.winner === 'neutral' && gameState.winner_player_id) {
    const winner = gameState.players[gameState.winner_player_id]
    return winner ? `${winner.display_name} Wins!` : 'Neutral Wins!'
  }
  return 'Game Over'
}

export default function GameOverScreen({ gameState, myPlayerId }: Props) {
  const allPlayers = Object.values(gameState.players)

  return (
    <div className="game-over">
      <h1 className="game-over__heading">{winnerHeading(gameState)}</h1>

      <div className="game-over__players">
        {allPlayers.map(p => (
          <div
            key={p.player_id}
            className={`game-over__player-row ${!p.is_alive ? 'game-over__player-row--dead' : ''} ${p.player_id === myPlayerId ? 'game-over__player-row--me' : ''}`}
          >
            <PlayerAvatar player={p} size={40} style={!p.is_alive ? { filter: 'grayscale(1)' } : undefined} />
            <span className="game-over__player-name">{p.display_name}</span>
            {p.role && (
              <span className="game-over__role-badge">{p.role.replace(/_/g, ' ')}</span>
            )}
          </div>
        ))}
      </div>

      {gameState.elimination_log.length > 0 && (
        <div className="game-over__log">
          <p className="game-over__log-heading">Elimination Log</p>
          {gameState.elimination_log.map((ev, i) => {
            const player = gameState.players[ev.player_id]
            return (
              <div key={i} className="game-over__log-row">
                <span className="game-over__log-round">R{ev.round}</span>
                <span className="game-over__log-name">{player?.display_name ?? ev.player_id}</span>
                <span className="game-over__log-cause">{CAUSE_LABELS[ev.cause] ?? ev.cause}</span>
              </div>
            )
          })}
        </div>
      )}

    </div>
  )
}
