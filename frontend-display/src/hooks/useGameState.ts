import { useState, useCallback, useRef, useEffect } from 'react'
import { useWebSocket, type WsStatus } from './useWebSocket'
import type { StrippedGameState, ServerMessage, NarrateMessage } from '../types/game'
import { useGameStore } from '../store/gameStore'

interface Options {
  gameId: string | null
  /** "display" for the TV client — no auth required. */
  playerId: string
  sessionToken?: string
  onNarrate?: (msg: NarrateMessage) => void
  /** Called when the first wolf kill vote is queued this night (PRD-012 §2.3) */
  onWolfKillQueued?: () => void
  /** Called when a player triggers a fun sound from their mobile sound board */
  onSoundTriggered?: (soundId: string, playerName: string) => void
}

export function useGameState({ gameId, playerId, sessionToken, onNarrate, onWolfKillQueued, onSoundTriggered }: Options) {
  const [gameState, setGameState] = useState<StrippedGameState | null>(null)
  const [status, setStatus] = useState<WsStatus>('closed')
  const lastStateIdRef = useRef(-1)

  // Reset state fence and stale game state when switching to a new game.
  // Without this, a new game starting at state_id=1 would be silently dropped
  // because the fence is still at the old game's final state_id (e.g. 100).
  useEffect(() => {
    lastStateIdRef.current = -1
    setGameState(null)
  }, [gameId])

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
    if (msg.type === 'narrate') {
      onNarrate?.(msg as NarrateMessage)
    }
    if (msg.type === 'wolf_kill_queued') {
      onWolfKillQueued?.()
    }
    if (msg.type === 'sound_triggered') {
      onSoundTriggered?.(msg.sound_id, msg.player_name)
    }
  }, [onNarrate, onWolfKillQueued, onSoundTriggered]) // eslint-disable-line react-hooks/exhaustive-deps

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
