import { useEffect, useRef, useState } from 'react'
import PlayerAvatar from '../PlayerAvatar/PlayerAvatar'
import { getCauseIcon } from '../../utils/elimination'
import type { StrippedGameState } from '../../types/game'
import './GameOverScreen.css'

interface Props {
  gameState: StrippedGameState
  audioUnlocked: boolean
  gameId: string
  hostSecret: string | null
  onPlayAgain: (newGameId: string, newHostSecret: string) => void
  onNewMatch: () => void
}

export default function GameOverScreen({ gameState, audioUnlocked, gameId, hostSecret, onPlayAgain, onNewMatch }: Props) {
  const [loading, setLoading] = useState<'play_again' | 'new_match' | null>(null)
  const [error, setError] = useState<string | null>(null)
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

  async function handlePlayAgain() {
    if (!hostSecret || loading) return
    setLoading('play_again')
    setError(null)
    try {
      const res = await fetch(`/api/games/${gameId}/rematch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host_secret: hostSecret }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        setError((body as { detail?: string }).detail ?? 'Could not start rematch.')
        return
      }
      const data = await res.json() as { new_game_id: string; new_host_secret: string }
      onPlayAgain(data.new_game_id, data.new_host_secret)
    } catch {
      setError('Network error.')
    } finally {
      setLoading(null)
    }
  }

  async function handleNewMatch() {
    if (!hostSecret || loading) return
    setLoading('new_match')
    try {
      await fetch(`/api/games/${gameId}/abandon`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host_secret: hostSecret }),
      })
    } catch { /* best-effort */ } finally {
      setLoading(null)
    }
    onNewMatch()
  }

  const players = Object.values(gameState.players)
  const timeline = gameState.post_match?.timeline ?? []
  const causeByPlayer = Object.fromEntries(
    gameState.elimination_log.map(e => [e.player_id, e.cause])
  )

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

      {/* Falling particles — gold confetti (village) or crimson mist (wolf) */}
      <div className={`game-over__particles ${isVillageWin ? 'game-over__particles--village' : 'game-over__particles--wolf'}`} aria-hidden="true">
        {Array.from({ length: 12 }).map((_, i) => (
          <span key={i} className="game-over__particle" />
        ))}
      </div>

      {/* Player reveal grid with role badges */}
      <div className="game-over__players">
        {players.map(player => (
          <div key={player.player_id} className="game-over__player">
            <PlayerAvatar player={player} />
            <p className="game-over__name">{player.display_name}</p>
            {player.role && (
              <span className="game-over__role-badge">{player.role}</span>
            )}
            {!player.is_alive && causeByPlayer[player.player_id] && (() => {
              const icon = getCauseIcon(causeByPlayer[player.player_id])
              return icon.type === 'image'
                ? <img className="game-over__cause-icon" src={icon.src} alt={icon.alt} />
                : <span className="game-over__cause-icon game-over__cause-icon--emoji" aria-hidden="true">{icon.char}</span>
            })()}
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

      {/* Host-only action buttons */}
      {hostSecret && (
        <div className="game-over__actions">
          {error && <p className="game-over__error">{error}</p>}
          <button
            className="game-over__btn game-over__btn--primary"
            disabled={!!loading}
            onClick={handlePlayAgain}
          >
            {loading === 'play_again' ? 'Starting…' : 'Play Again'}
          </button>
          <button
            className="game-over__btn game-over__btn--secondary"
            disabled={!!loading}
            onClick={handleNewMatch}
          >
            {loading === 'new_match' ? 'Leaving…' : 'New Match'}
          </button>
        </div>
      )}
    </div>
  )
}
