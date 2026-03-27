import { useEffect, useRef } from 'react'
import PlayerAvatar from '../PlayerAvatar/PlayerAvatar'
import type { StrippedGameState } from '../../types/game'
import './NightResolution.css'

interface Props {
  gameState: StrippedGameState
  onComplete: () => void
}

const DURATION_MS = 4000

export default function NightResolution({ gameState, onComplete }: Props) {
  const roosterRef = useRef<HTMLAudioElement>(null)

  // Night eliminations in the current round
  const nightDeaths = gameState.elimination_log.filter(
    e => e.phase === 'night' && e.round === gameState.round,
  )
  const hasDeaths = nightDeaths.length > 0

  useEffect(() => {
    roosterRef.current?.play().catch(() => {})
    const t = setTimeout(onComplete, DURATION_MS)
    return () => clearTimeout(t)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="night-resolution">
      <audio ref={roosterRef} src="/audio/rooster.mp3" preload="auto" />

      {/* Main announcement text */}
      <p className="night-resolution__headline">
        {hasDeaths ? 'A body is discovered…' : 'Dawn breaks over the village…'}
      </p>

      {/* Death reveals */}
      {nightDeaths.map((event, i) => {
        const player = gameState.players[event.player_id]
        if (!player) return null
        return (
          <div
            key={event.player_id}
            className="night-resolution__death"
            style={{ animationDelay: `${600 + i * 400}ms` }}
          >
            <PlayerAvatar player={player} size={96} />
            <div className="night-resolution__claw-mark" aria-hidden="true">✕</div>
            <p className="night-resolution__player-name">{player.display_name}</p>
          </div>
        )
      })}
    </div>
  )
}
