import { useEffect, useRef, useState } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import PlayerAvatar from '../PlayerAvatar/PlayerAvatar'
import LobbyConfigPanel from '../LobbyConfigPanel/LobbyConfigPanel'
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
  // roster is updated in real-time via match_data on every player join/leave.
  // gameState.players only updates on sync/update (not sent during lobby phase).
  const roster = useGameStore(state => state.roster)
  const connectedPlayers = roster.filter(p => p.is_connected)
  const playerCount = connectedPlayers.length
  const canStart = playerCount >= 5
  const [starting, setStarting] = useState(false)
  const [kickingIds, setKickingIds] = useState(new Set<string>())

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

  async function handleKick(playerId: string) {
    if (!gameId || !hostSecret || kickingIds.has(playerId)) return
    setKickingIds(prev => new Set([...prev, playerId]))
    try {
      await fetch(`/api/games/${gameId}/players/${playerId}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host_secret: hostSecret }),
      })
    } finally {
      setKickingIds(prev => { const n = new Set(prev); n.delete(playerId); return n })
    }
  }

  // Track which player_ids are new arrivals for pop-in animation
  const knownIdsRef = useRef(new Set<string>())
  const [newIds, setNewIds] = useState(new Set<string>())

  useEffect(() => {
    const currentIds = new Set(connectedPlayers.map(p => p.player_id))
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
  }, [connectedPlayers.map(p => p.player_id).join(',')]) // eslint-disable-line react-hooks/exhaustive-deps

  const isDealing = gameState.phase === 'role_deal'

  return (
    <div className="lobby-screen">
      {/* Top-right: player count badge — PRD-003 §6 */}
      <div className="lobby-screen__count">
        {playerCount} active / {roster.length} joined
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

      {/* Campfire + avatar parade (connected players only) */}
      <div className="lobby-screen__parade">
        <div className="lobby-screen__campfire">🔥</div>
        <div className="lobby-screen__avatars">
          {connectedPlayers.map((p: PlayerRosterEntry) => (
            <PlayerAvatar
              key={p.player_id}
              player={p}
              className={newIds.has(p.player_id) ? 'avatar-pop-in' : ''}
            />
          ))}
        </div>
      </div>

      {/* Player roster — all entries with connection status + host kick controls */}
      {roster.length > 0 && (
        <div className="lobby-screen__roster">
          {roster.map((p: PlayerRosterEntry) => (
            <div
              key={p.player_id}
              className={`lobby-screen__roster-row${p.is_connected ? '' : ' lobby-screen__roster-row--offline'}`}
            >
              <span className={`lobby-screen__dot${p.is_connected ? ' lobby-screen__dot--on' : ''}`} />
              <PlayerAvatar player={p} size={28} />
              <span className="lobby-screen__roster-name">{p.display_name}</span>
              {!p.is_connected && hostSecret && (
                <button
                  className="lobby-screen__kick-btn"
                  disabled={kickingIds.has(p.player_id)}
                  onClick={() => handleKick(p.player_id)}
                  aria-label={`Remove ${p.display_name}`}
                >
                  ✕
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Config panel: difficulty + timers — PRD-005 */}
      <LobbyConfigPanel
        config={gameState.config}
        hostSecret={hostSecret}
        gameId={gameId}
      />

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
