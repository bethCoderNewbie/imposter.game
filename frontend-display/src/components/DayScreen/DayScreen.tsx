import PhaseTimer from '../PhaseTimer/PhaseTimer'
import PlayerCard from './PlayerCard'
import VoteWeb from '../VoteWeb/VoteWeb'
import type { StrippedGameState } from '../../types/game'
import './DayScreen.css'

interface Props {
  gameState: StrippedGameState
  /** Votes snapshot frozen at day_vote close — passed to VoteWeb for reveal-all-at-once */
  frozenVotes: Record<string, string> | null
  audioUnlocked: boolean
}

export default function DayScreen({ gameState, frozenVotes, audioUnlocked }: Props) {
  const players = Object.values(gameState.players)
  const isVoting = gameState.phase === 'day_vote'

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
        <PhaseTimer
          timerEndsAt={gameState.timer_ends_at}
          className="day-screen__timer"
          enableCountdownBeep={isVoting}
          audioUnlocked={audioUnlocked}
        />
      </div>

      {/* Player grid — relative so VoteWeb SVG can overlay it */}
      <div className={`day-screen__grid${isVoting ? ' day-screen__grid--voting' : ''}`} id="player-grid">
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
