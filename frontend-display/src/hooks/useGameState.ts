import { useState, useCallback, useRef } from 'react'
import { useWebSocket, type WsStatus } from './useWebSocket'
import type { StrippedGameState, ServerMessage } from '../types/game'
import { useGameStore } from '../store/gameStore'

interface Options {
  gameId: string | null
  /** "display" for the TV client — no auth required. */
  playerId: string
  sessionToken?: string
}

export function useGameState({ gameId, playerId, sessionToken }: Options) {
  const [gameState, setGameState] = useState<StrippedGameState | null>(null)
  const [status, setStatus] = useState<WsStatus>('closed')
  const lastStateIdRef = useRef(-1)

  const proto = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = gameId
    ? `${proto}//${window.location.host}/ws/${gameId}/${playerId}`
    : null

  const handleMessage = useCallback((data: unknown) => {
    const msg = data as ServerMessage
    if (msg.type === 'sync' || msg.type === 'update') {
      if (msg.state_id > lastStateIdRef.current) {
        lastStateIdRef.current = msg.state_id
        setGameState(msg.state)
        if (msg.type === 'sync') {
          useGameStore.getState().setRoster(Object.values(msg.state.players))
        }
      }
    }
    if (msg.type === 'match_data') {
      useGameStore.getState().setRoster(msg.players)
    }
    // error messages are logged; surface to UI if needed
    if (msg.type === 'error') {
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

  return { gameState, sendIntent, status }
}
