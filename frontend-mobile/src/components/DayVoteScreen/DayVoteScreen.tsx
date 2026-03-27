import { useState } from 'react'
import { useHaptics } from '../../hooks/useHaptics'
import PlayerAvatar from '../PlayerAvatar/PlayerAvatar'
import type { PlayerState, StrippedGameState } from '../../types/game'
import './DayVoteScreen.css'

interface Props {
  gameState: StrippedGameState
  myPlayer: PlayerState
  sendIntent: (payload: Record<string, unknown>) => void
}

export default function DayVoteScreen({ gameState, myPlayer, sendIntent }: Props) {
  const [votedId, setVotedId] = useState<string | null>(myPlayer.vote_target_id ?? null)
  const { vibrate } = useHaptics()

  const livingPlayers = Object.values(gameState.players).filter(
    p => p.is_alive && p.player_id !== myPlayer.player_id,
  )

  function handleVote(targetId: string) {
    vibrate(200)
    setVotedId(targetId)
    sendIntent({ type: 'submit_day_vote', target_id: targetId })
  }

  return (
    <div className="day-vote">
      <div className="day-vote__header">
        <span className="day-vote__round">Day {gameState.round}</span>
        <h2 className="day-vote__title">Vote to Eliminate</h2>
      </div>

      <div className="day-vote__list">
        {livingPlayers.map(p => (
          <div key={p.player_id} className="day-vote__row">
            <PlayerAvatar player={p} />
            <span className="day-vote__name">{p.display_name}</span>
            {votedId === p.player_id ? (
              <span className="day-vote__voted">✓ Voted</span>
            ) : (
              <button
                className="day-vote__btn"
                onClick={() => handleVote(p.player_id)}
              >
                {votedId ? 'Change Vote' : 'Vote'}
              </button>
            )}
          </div>
        ))}
      </div>

      {votedId && (
        <p className="day-vote__status">
          Vote cast — waiting for others…
        </p>
      )}
    </div>
  )
}
