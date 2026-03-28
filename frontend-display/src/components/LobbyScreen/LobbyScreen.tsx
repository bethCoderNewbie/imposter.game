import { useEffect, useRef, useState } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import PlayerAvatar from '../PlayerAvatar/PlayerAvatar'
import type { StrippedGameState, PlayerRosterEntry } from '../../types/game'
import { useGameStore } from '../../store/gameStore'
import './LobbyScreen.css'

interface Props {
  gameState: StrippedGameState
  hostSecret?: string
  gameId?: string
}

// VITE_HOST_IP is baked at Docker build time (e.g. http://192.168.1.100).
// Falls back to window.location.origin so dev mode and direct-IP access still work.
const HOST_BASE: string = import.meta.env.VITE_HOST_IP || window.location.origin

export default function LobbyScreen({ gameState, hostSecret, gameId }: Props) {
  const joinUrl = `${HOST_BASE}/?g=${gameState.game_id}`
  const players = useGameStore(state => state.roster)
  const playerCount = players.length
  const canStart = playerCount >= 5
  const [starting, setStarting] = useState(false)

  async function handleStart() {
    if (!gameId || starting) return
    setStarting(true)
    try {
      await fetch(`/api/games/${gameId}/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(hostSecret ? { host_secret: hostSecret } : {}),
      })
    } finally {
      setStarting(false)
    }
  }

  // Track which player_ids are new arrivals for pop-in animation
  const knownIdsRef = useRef(new Set<string>())
  const [newIds, setNewIds] = useState(new Set<string>())

  useEffect(() => {
    const currentIds = new Set(players.map(p => p.player_id))
    const arrived = new Set<string>()
    currentIds.forEach(id => {
      if (!knownIdsRef.current.has(id)) arrived.add(id)
    })
    if (arrived.size > 0) {
      setNewIds(prev => new Set([...prev, ...arrived]))
      // Clear pop-in flag after animation completes
      setTimeout(() => {
        setNewIds(prev => {
          const next = new Set(prev)
          arrived.forEach(id => next.delete(id))
          return next
        })
      }, 500)
    }
    knownIdsRef.current = currentIds
  }, [players.map(p => p.player_id).join(',')]) // eslint-disable-line react-hooks/exhaustive-deps

  const isDealing = gameState.phase === 'role_deal'

  return (
    <div className="lobby-screen">
      {/* Top-right: player count badge — PRD-003 §6 */}
      <div className="lobby-screen__count">
        {playerCount} / {gameState.config.player_count || 18} joined
      </div>

      {/* Center: QR code + join URL + room code */}
      <div className="lobby-screen__join">
        <QRCodeSVG
          value={joinUrl}
          size={300}
          bgColor="#000000"
          fgColor="#ffffff"
          level="M"
          className="lobby-screen__qr"
        />
        <p className="lobby-screen__url">{HOST_BASE.replace(/^https?:\/\//, '')}/?g=</p>
        <p className="lobby-screen__code">{gameState.game_id}</p>
      </div>

      {/* Campfire + avatar parade */}
      <div className="lobby-screen__parade">
        <div className="lobby-screen__campfire">🔥</div>
        <div className="lobby-screen__avatars">
          {players.map((p: PlayerRosterEntry) => (
            <PlayerAvatar
              key={p.player_id}
              player={p}
              className={newIds.has(p.player_id) ? 'avatar-pop-in' : ''}
            />
          ))}
        </div>
      </div>

      {/* Bottom: status + optional Start button */}
      <div className="lobby-screen__status">
        {isDealing ? (
          'Dealing roles…'
        ) : hostSecret ? (
          <button
            className="lobby-screen__start-btn"
            disabled={!canStart || starting}
            onClick={handleStart}
          >
            {starting ? 'Starting…' : canStart ? 'Start Game' : `Need ${5 - playerCount} more player${5 - playerCount !== 1 ? 's' : ''}`}
          </button>
        ) : (
          'Waiting for host to start'
        )}
      </div>
    </div>
  )
}
