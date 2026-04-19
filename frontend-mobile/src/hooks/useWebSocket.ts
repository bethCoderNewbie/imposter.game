import { useEffect, useRef, useCallback } from 'react'

export type WsStatus = 'connecting' | 'open' | 'closed' | 'ssl_error'

interface Options {
  url: string | null
  sessionToken?: string
  onMessage: (data: unknown) => void
  onStatusChange?: (status: WsStatus) => void
}

const BASE_RETRY_MS = 1000
const MAX_RETRY_MS = 30_000

export function useWebSocket({ url, sessionToken, onMessage, onStatusChange }: Options) {
  const wsRef = useRef<WebSocket | null>(null)
  const retriesRef = useRef(0)
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

      const connectTime = Date.now()
      let authExchanged = false

      ws.onopen = () => {
        authExchanged = true
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
        if (!authExchanged && Date.now() - connectTime < 200) {
          onStatusRef.current?.('ssl_error')
          return
        }
        onStatusRef.current?.('closed')
        if (!closed) {
          const delay = Math.min(BASE_RETRY_MS * 2 ** retriesRef.current, MAX_RETRY_MS)
          retriesRef.current++
          retryTimeout = setTimeout(connect, delay)
        }
      }

      ws.onerror = () => { ws.close() }
    }

    connect()

    return () => {
      closed = true
      clearTimeout(retryTimeout)
      wsRef.current?.close()
    }
  }, [url, sessionToken])

  return { send }
}
