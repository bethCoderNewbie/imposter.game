import PhaseTimer from '../PhaseTimer/PhaseTimer'
import PlayerCard from './PlayerCard'
import VoteWeb from '../VoteWeb/VoteWeb'
import type { StrippedGameState } from '../../types/game'
import './DayScreen.css'

/**
 * Compute --u (circle unit, vmin) for the flex-wrap player grid.
 *
 * Strategy — single-row first:
 *   1. Compute the largest u where ALL players fit in one row.
 *   2. If that u ≥ 7vmin (readable), use it → guaranteed single row.
 *   3. Otherwise fall back to multi-row: find the largest u whose total
 *      grid height stays within 80vmin using flex-wrap row counts.
 *
 * circle diameter = --s = 1.4 * u
 * items per row   = floor((container + gap) / (circle + gap))
 * rows            = ceil(playerCount / itemsPerRow)
 */
function computeHexUnit(playerCount: number): number {
  if (playerCount <= 0) return 10

  const containerVmin = 90
  const availableVmin = 80
  const gapVmin       = 4.5   // matches gap in DayScreen.css
  const circleRatio   = 1.4   // --s = 1.4 * u
  const uMinSingle    = 7     // smallest u still readable in single row

  // ── 1. Single-row solution ───────────────────────────────────────────────
  // Largest u where floor((container + gap) / (u*ratio + gap)) >= playerCount
  const uSingle = Math.floor(
    ((containerVmin + gapVmin) / playerCount - gapVmin) / circleRatio
  )
  if (uSingle >= uMinSingle) return uSingle

  // ── 2. Multi-row fallback ────────────────────────────────────────────────
  function ipr(u: number): number {
    return Math.max(1, Math.floor((containerVmin + gapVmin) / (u * circleRatio + gapVmin)))
  }

  for (let u = 30; u >= 5; u--) {
    const rows       = Math.ceil(playerCount / ipr(u))
    const circleH    = u * circleRatio
    const rowHeight  = circleH + u * 0.22   // circle + name label
    const gridHeight = rows * rowHeight + Math.max(0, rows - 1) * gapVmin
    if (gridHeight <= availableVmin) return u
  }
  return 5
}

interface Props {
  gameState: StrippedGameState
  /** Votes snapshot frozen at day_vote close — passed to VoteWeb for reveal-all-at-once */
  frozenVotes: Record<string, string> | null
  audioUnlocked: boolean
  soundPlayerId: string | null
}

export default function DayScreen({ gameState, frozenVotes, audioUnlocked, soundPlayerId }: Props) {
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

  const hexUnit = computeHexUnit(players.length)
  const causeByPlayer = Object.fromEntries(
    gameState.elimination_log.map(e => [e.player_id, e.cause])
  )

  return (
    <div className="day-screen">
      {/* Parallax background — behind all game content */}
      <div
        className="day-parallax"
        aria-hidden="true"
        style={{
          '--img-bg':     `url("${import.meta.env.BASE_URL}images/background.jpg")`,
          '--img-fg':     `url("${import.meta.env.BASE_URL}images/foreground.png")`,
          '--img-hills':  `url("${import.meta.env.BASE_URL}images/hills.png")`,
          '--img-rocks1': `url("${import.meta.env.BASE_URL}images/rocks1.png")`,
          '--img-rocks2': `url("${import.meta.env.BASE_URL}images/rocks2.png")`,
        } as React.CSSProperties}
      >
        <div className="day-parallax__layer day-parallax__rocks2" />
        <div className="day-parallax__layer day-parallax__rocks1" />
        <div className="day-parallax__layer day-parallax__hills" />
        <div className="day-parallax__layer day-parallax__foreground" />
      </div>

      {/* Top-center: round label + timer — PRD-003 §6 */}
      <div className="day-screen__header">
        <span className="day-screen__round">Day {gameState.round}</span>
        <PhaseTimer
          timerEndsAt={gameState.timer_ends_at}
          timerPaused={gameState.timer_paused}
          timerRemainingSeconds={gameState.timer_remaining_seconds}
          className="day-screen__timer"
          enableCountdownBeep={true}
          audioUnlocked={audioUnlocked}
        />
      </div>

      {/* Player grid — --u drives hex size; computed from player count */}
      <div
        className={`day-screen__grid${isVoting ? ' day-screen__grid--voting' : ''}`}
        id="player-grid"
        style={{ ['--u' as string]: `${hexUnit}vmin` }}
      >
        {players.map((player, index) => (
          <PlayerCard
            key={player.player_id}
            player={player}
            voteCount={voteCounts[player.player_id] ?? 0}
            hasMajority={(voteCounts[player.player_id] ?? 0) > majorityThreshold}
            index={index}
            isSoundActive={soundPlayerId === player.player_id}
            eliminationCause={causeByPlayer[player.player_id] ?? null}
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
