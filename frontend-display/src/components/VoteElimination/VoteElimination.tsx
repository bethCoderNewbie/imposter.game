import { useEffect } from 'react'
import PlayerAvatar from '../PlayerAvatar/PlayerAvatar'
import { getCauseIcon } from '../../utils/elimination'
import type { StrippedGameState } from '../../types/game'
import './VoteElimination.css'

interface Props {
  gameState: StrippedGameState
  onComplete: () => void
}

const ELIMINATION_DURATION_MS = 10000
const TIE_DURATION_MS = 5000

export default function VoteElimination({ gameState, onComplete }: Props) {
  // Day eliminations from village vote in the current round
  const dayDeaths = gameState.elimination_log.filter(
    e => e.phase === 'day' && e.round === gameState.round && e.cause === 'village_vote',
  )
  const hasElimination = dayDeaths.length > 0
  const duration = hasElimination ? ELIMINATION_DURATION_MS : TIE_DURATION_MS

  useEffect(() => {
    const t = setTimeout(onComplete, duration)
    return () => clearTimeout(t)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="vote-elimination">
      <p className="vote-elimination__headline">
        {hasElimination ? 'The village has spoken…' : 'No consensus reached…'}
      </p>

      {dayDeaths.map((event, i) => {
        const player = gameState.players[event.player_id]
        if (!player) return null
        return (
          <div
            key={event.player_id}
            className="vote-elimination__player"
            style={{ animationDelay: `${600 + i * 400}ms` }}
          >
            <PlayerAvatar player={player} size={96} />
            {(() => {
              const icon = getCauseIcon(event.cause)
              return icon.type === 'image'
                ? <img className="vote-elimination__cause-icon" src={icon.src} alt={icon.alt} />
                : <div className="vote-elimination__cause-icon vote-elimination__cause-icon--emoji" aria-hidden="true">{icon.char}</div>
            })()}
            <p className="vote-elimination__player-name">{player.display_name}</p>
          </div>
        )
      })}
    </div>
  )
}
