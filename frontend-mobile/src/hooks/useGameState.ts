import { useState, useCallback, useRef, useEffect } from 'react'
import { useWebSocket, type WsStatus } from './useWebSocket'
import type { GridRippleMessage, HintPayload, RedirectMessage, StrippedGameState, ServerMessage, PlayerRosterEntry } from '../types/game'
import { getWsBase } from '../utils/backend'

interface Options {
  gameId: string | null
  playerId: string
  sessionToken?: string
  onHint?: (hint: HintPayload) => void
  onRedirect?: (msg: RedirectMessage) => void
  onRipple?: (msg: GridRippleMessage) => void
}

export function useGameState({ gameId, playerId, sessionToken, onHint, onRedirect, onRipple }: Options) {
  const [gameState, setGameState] = useState<StrippedGameState | null>(null)
  const [roster, setRoster] = useState<PlayerRosterEntry[]>([])
  const [status, setStatus] = useState<WsStatus>('closed')
  const lastStateIdRef = useRef(-1)
  const onHintRef = useRef(onHint)
  onHintRef.current = onHint
  const onRedirectRef = useRef(onRedirect)
  onRedirectRef.current = onRedirect
  const onRippleRef = useRef(onRipple)
  onRippleRef.current = onRipple

  // Reset state fence and stale game state when switching to a new game.
  // Without this, a rematch (new game starting at state_id=1) is silently
  // dropped when lastStateIdRef is still at the old game's final state_id.
  useEffect(() => {
    lastStateIdRef.current = -1
    setGameState(null)
    setRoster([])
  }, [gameId])

  const url = gameId && playerId
    ? `${getWsBase()}/ws/${gameId}/${playerId}`
    : null

  const handleMessage = useCallback((data: unknown) => {
    const msg = data as ServerMessage
    if (msg.type === 'sync' || msg.type === 'update') {
      if (msg.state_id > lastStateIdRef.current) {
        lastStateIdRef.current = msg.state_id
        setGameState(msg.state)
        if (msg.type === 'sync') {
          setRoster(Object.values(msg.state.players).map(p => ({
            player_id: p.player_id,
            display_name: p.display_name,
            avatar_id: p.avatar_id,
            photo_url: p.photo_url,
            is_connected: p.is_connected,
          })))
        }
      }
    } else if (msg.type === 'match_data') {
      setRoster(msg.players)
    } else if (msg.type === 'hint_reward') {
      onHintRef.current?.(msg as HintPayload)
    } else if (msg.type === 'redirect') {
      onRedirectRef.current?.(msg as RedirectMessage)
    } else if (msg.type === 'grid_ripple') {
      onRippleRef.current?.(msg as GridRippleMessage)
    } else if (msg.type === 'error') {
      console.warn('[WS error]', msg.code, msg.message)
    }
  }, [])

  const { send } = useWebSocket({
    url,
    sessionToken,
    onMessage: handleMessage,
    onStatusChange: setStatus,
  })

  const sendIntent = useCallback(
    (payload: Record<string, unknown>) => { send(payload) },
    [send],
  )

  return { gameState, roster, sendIntent, status }
}
