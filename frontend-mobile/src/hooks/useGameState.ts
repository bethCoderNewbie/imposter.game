import { useState, useCallback, useRef } from 'react'
import { useWebSocket, type WsStatus } from './useWebSocket'
import type { HintPayload, RedirectMessage, StrippedGameState, ServerMessage } from '../types/game'

interface Options {
  gameId: string | null
  playerId: string
  sessionToken?: string
  onHint?: (hint: HintPayload) => void
  onRedirect?: (msg: RedirectMessage) => void
}

export function useGameState({ gameId, playerId, sessionToken, onHint, onRedirect }: Options) {
  const [gameState, setGameState] = useState<StrippedGameState | null>(null)
  const [status, setStatus] = useState<WsStatus>('closed')
  const lastStateIdRef = useRef(-1)
  const onHintRef = useRef(onHint)
  onHintRef.current = onHint
  const onRedirectRef = useRef(onRedirect)
  onRedirectRef.current = onRedirect

  const proto = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = gameId && playerId
    ? `${proto}//${window.location.host}/ws/${gameId}/${playerId}`
    : null

  const handleMessage = useCallback((data: unknown) => {
    const msg = data as ServerMessage
    if (msg.type === 'sync' || msg.type === 'update') {
      if (msg.state_id > lastStateIdRef.current) {
        lastStateIdRef.current = msg.state_id
        setGameState(msg.state)
      }
    } else if (msg.type === 'hint_reward') {
      onHintRef.current?.(msg as HintPayload)
    } else if (msg.type === 'redirect') {
      onRedirectRef.current?.(msg as RedirectMessage)
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

  return { gameState, sendIntent, status }
}
