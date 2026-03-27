import { useTimer } from '../../hooks/useTimer'
import PlayerCard from './PlayerCard'
import VoteWeb from '../VoteWeb/VoteWeb'
import type { StrippedGameState } from '../../types/game'
import './DayScreen.css'

interface Props {
  gameState: StrippedGameState
  /** Votes snapshot frozen at day_vote close — passed to VoteWeb for reveal-all-at-once */
  frozenVotes: Record<string, string> | null
}

export default function DayScreen({ gameState, frozenVotes }: Props) {
  const { secondsRemaining, isWarning, isCritical } = useTimer(gameState.timer_ends_at)

  const players = Object.values(gameState.players)
  const isVoting = gameState.phase === 'day_vote'

  const mm = String(Math.floor(secondsRemaining / 60)).padStart(2, '0')
  const ss = String(secondsRemaining % 60).padStart(2, '0')
  const timerClass = isCritical ? 'timer--critical' : isWarning ? 'timer--warning' : ''

  // Vote tallies (live during day_vote; frozen after voting closes)
  const votes = isVoting ? gameState.day_votes : (frozenVotes ?? {})
  const voteCounts: Record<string, number> = {}
  Object.values(votes).forEach(targetId => {
    voteCounts[targetId] = (voteCounts[targetId] ?? 0) + 1
  })
  const livingCount = players.filter(p => p.is_alive).length
  const majorityThreshold = livingCount > 0 ? livingCount / 2 : Infinity

  return (
    <div className="day-screen">
      {/* Top-center: round label + timer — PRD-003 §6 */}
      <div className="day-screen__header">
        <span className="day-screen__round">Day {gameState.round}</span>
        <span className={`day-screen__timer ${timerClass}`}>{mm}:{ss}</span>
      </div>

      {/* Player grid — relative so VoteWeb SVG can overlay it */}
      <div className="day-screen__grid" id="player-grid">
        {players.map(player => (
          <PlayerCard
            key={player.player_id}
            player={player}
            voteCount={voteCounts[player.player_id] ?? 0}
            hasMajority={(voteCounts[player.player_id] ?? 0) > majorityThreshold}
          />
        ))}

        {/* VoteWeb SVG overlay — visible once frozenVotes is set (reveal-all-at-once) */}
        {frozenVotes && (
          <VoteWeb votes={frozenVotes} />
        )}
      </div>

      {/* Bottom: phase label — PRD-003 §2.2 */}
      <div className="day-screen__phase-label">
        {isVoting ? 'Voting' : 'Discussion'}
      </div>
    </div>
  )
}
