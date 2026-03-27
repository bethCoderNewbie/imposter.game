import { useEffect, useRef } from 'react'
import PlayerAvatar from '../PlayerAvatar/PlayerAvatar'
import type { StrippedGameState } from '../../types/game'
import './GameOverScreen.css'

interface Props {
  gameState: StrippedGameState
  audioUnlocked: boolean
}

export default function GameOverScreen({ gameState, audioUnlocked }: Props) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const isVillageWin = gameState.winner === 'village'

  // Apply winner class to root substrate
  useEffect(() => {
    document.documentElement.className = isVillageWin ? 'winner-village' : 'winner-wolf'
    return () => { document.documentElement.className = '' }
  }, [isVillageWin])

  useEffect(() => {
    if (audioUnlocked && audioRef.current) {
      audioRef.current.volume = 0.6
      audioRef.current.play().catch(() => {})
    }
  }, [audioUnlocked])

  const players = Object.values(gameState.players)
  const timeline = gameState.post_match?.timeline ?? []

  return (
    <div className="game-over">
      {/* Victory / defeat audio */}
      <audio
        ref={audioRef}
        src={isVillageWin ? '/audio/victory-fanfare.mp3' : '/audio/wolf-howl.mp3'}
        preload="auto"
      />

      {/* Winning headline — PRD-003 §2.2 */}
      <h1 className={`game-over__headline ${isVillageWin ? 'game-over__headline--village' : 'game-over__headline--wolf'}`}>
        {isVillageWin ? 'THE VILLAGE SURVIVES' : 'THE WOLVES DEVOUR THE VILLAGE'}
      </h1>

      {/* Player reveal grid with role badges */}
      <div className="game-over__players">
        {players.map(player => (
          <div key={player.player_id} className="game-over__player">
            <PlayerAvatar player={player} />
            <p className="game-over__name">{player.display_name}</p>
            {player.role && (
              <span className="game-over__role-badge">{player.role}</span>
            )}
          </div>
        ))}
      </div>

      {/* Elimination timeline — staggered reveal-flicker */}
      {timeline.length > 0 && (
        <div className="game-over__timeline">
          {timeline.map((event, i) => (
            <p
              key={i}
              className="game-over__timeline-entry"
              style={{ animationDelay: `${i * 600}ms` }}
            >
              {event.display_text}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}
