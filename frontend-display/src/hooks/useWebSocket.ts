import { useEffect, useRef, useCallback } from 'react'

export type WsStatus = 'connecting' | 'open' | 'closed'

interface Options {
  /** Full WS URL. Pass null to disconnect / not connect. */
  url: string | null
  /** If provided, sent as {"type":"auth","session_token":"..."} immediately on open. */
  sessionToken?: string
  onMessage: (data: unknown) => void
  onStatusChange?: (status: WsStatus) => void
}

const MAX_RETRIES = 5
const RETRY_DELAY_MS = 2000

export function useWebSocket({ url, sessionToken, onMessage, onStatusChange }: Options) {
  const wsRef = useRef<WebSocket | null>(null)
  const retriesRef = useRef(0)
  // Keep stable refs to callbacks so effects don't re-run on every render
  const onMessageRef = useRef(onMessage)
  const onStatusRef = useRef(onStatusChange)
  onMessageRef.current = onMessage
  onStatusRef.current = onStatusChange

  const send = useCallback((payload: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(payload))
    }
  }, [])

  useEffect(() => {
    if (!url) return

    let closed = false
    let retryTimeout: ReturnType<typeof setTimeout>

    function connect() {
      if (closed) return
      const ws = new WebSocket(url!)
      wsRef.current = ws
      onStatusRef.current?.('connecting')

      ws.onopen = () => {
        retriesRef.current = 0
        onStatusRef.current?.('open')
        if (sessionToken) {
          ws.send(JSON.stringify({ type: 'auth', session_token: sessionToken }))
        }
      }

      ws.onmessage = (event: MessageEvent) => {
        try {
          onMessageRef.current(JSON.parse(event.data as string))
        } catch {
          // ignore malformed frames
        }
      }

      ws.onclose = () => {
        onStatusRef.current?.('closed')
        if (!closed && retriesRef.current < MAX_RETRIES) {
          retriesRef.current++
          retryTimeout = setTimeout(connect, RETRY_DELAY_MS)
        }
      }

      ws.onerror = () => {
        ws.close()
      }
    }

    connect()

    return () => {
      closed = true
      clearTimeout(retryTimeout)
      wsRef.current?.close()
    }
  }, [url, sessionToken]) // intentionally omit callback refs

  return { send }
}
