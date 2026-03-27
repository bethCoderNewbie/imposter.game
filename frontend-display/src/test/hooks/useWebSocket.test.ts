import { renderHook, act } from '@testing-library/react'
import { useWebSocket } from '../../hooks/useWebSocket'

// ── FakeWebSocket ────────────────────────────────────────────────────────────

class FakeWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  static instances: FakeWebSocket[] = []

  readyState = FakeWebSocket.CONNECTING
  onopen: ((ev: Event) => void) | null = null
  onclose: ((ev: CloseEvent) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  onerror: ((ev: Event) => void) | null = null
  send = vi.fn()
  close = vi.fn().mockImplementation(() => {
    this.readyState = FakeWebSocket.CLOSED
  })

  constructor(public url: string) {
    FakeWebSocket.instances.push(this)
  }

  triggerOpen() {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.(new Event('open'))
  }

  triggerClose() {
    this.readyState = FakeWebSocket.CLOSED
    this.onclose?.(new CloseEvent('close'))
  }

  triggerMessage(data: unknown) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) }))
  }

  triggerRawMessage(raw: string) {
    this.onmessage?.(new MessageEvent('message', { data: raw }))
  }

  triggerError() {
    this.onerror?.(new Event('error'))
  }

  static get latest(): FakeWebSocket {
    return FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
  }

  static reset() {
    FakeWebSocket.instances = []
  }
}

// ── Setup / teardown ─────────────────────────────────────────────────────────

beforeEach(() => {
  FakeWebSocket.reset()
  vi.useFakeTimers()
  vi.stubGlobal('WebSocket', FakeWebSocket)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

// ── Tests ────────────────────────────────────────────────────────────────────

describe('useWebSocket', () => {
  it('does not connect when url is null', () => {
    renderHook(() => useWebSocket({ url: null, onMessage: vi.fn() }))
    expect(FakeWebSocket.instances).toHaveLength(0)
  })

  it('creates WebSocket with correct url', () => {
    renderHook(() => useWebSocket({ url: 'ws://test/ws/game/display', onMessage: vi.fn() }))
    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(FakeWebSocket.instances[0].url).toBe('ws://test/ws/game/display')
  })

  it('calls onStatusChange("connecting") before open', () => {
    const onStatusChange = vi.fn()
    renderHook(() => useWebSocket({ url: 'ws://test', onMessage: vi.fn(), onStatusChange }))
    expect(onStatusChange).toHaveBeenCalledWith('connecting')
  })

  it('calls onStatusChange("open") on ws open', () => {
    const onStatusChange = vi.fn()
    renderHook(() => useWebSocket({ url: 'ws://test', onMessage: vi.fn(), onStatusChange }))
    act(() => { FakeWebSocket.latest.triggerOpen() })
    expect(onStatusChange).toHaveBeenCalledWith('open')
  })

  it('sends auth message on open when sessionToken provided', () => {
    renderHook(() => useWebSocket({ url: 'ws://test', onMessage: vi.fn(), sessionToken: 'tok123' }))
    act(() => { FakeWebSocket.latest.triggerOpen() })
    expect(FakeWebSocket.latest.send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'auth', session_token: 'tok123' })
    )
  })

  it('does not send auth when no sessionToken', () => {
    renderHook(() => useWebSocket({ url: 'ws://test', onMessage: vi.fn() }))
    act(() => { FakeWebSocket.latest.triggerOpen() })
    expect(FakeWebSocket.latest.send).not.toHaveBeenCalled()
  })

  it('calls onMessage with parsed JSON on message', () => {
    const onMessage = vi.fn()
    renderHook(() => useWebSocket({ url: 'ws://test', onMessage }))
    act(() => { FakeWebSocket.latest.triggerMessage({ type: 'ping', value: 42 }) })
    expect(onMessage).toHaveBeenCalledWith({ type: 'ping', value: 42 })
  })

  it('ignores malformed JSON frames without throwing', () => {
    const onMessage = vi.fn()
    renderHook(() => useWebSocket({ url: 'ws://test', onMessage }))
    expect(() => {
      act(() => { FakeWebSocket.latest.triggerRawMessage('not-valid-json{{{') })
    }).not.toThrow()
    expect(onMessage).not.toHaveBeenCalled()
  })

  it('calls onStatusChange("closed") on ws close', () => {
    const onStatusChange = vi.fn()
    renderHook(() => useWebSocket({ url: 'ws://test', onMessage: vi.fn(), onStatusChange }))
    act(() => { FakeWebSocket.latest.triggerClose() })
    expect(onStatusChange).toHaveBeenCalledWith('closed')
  })

  it('schedules retry after close (RETRY_DELAY_MS = 2000)', () => {
    renderHook(() => useWebSocket({ url: 'ws://test', onMessage: vi.fn() }))
    act(() => { FakeWebSocket.latest.triggerClose() })
    expect(FakeWebSocket.instances).toHaveLength(1)
    act(() => { vi.advanceTimersByTime(2000) })
    expect(FakeWebSocket.instances).toHaveLength(2)
  })

  it('retries up to MAX_RETRIES = 5 times', () => {
    renderHook(() => useWebSocket({ url: 'ws://test', onMessage: vi.fn() }))
    for (let i = 0; i < 5; i++) {
      act(() => { FakeWebSocket.latest.triggerClose() })
      act(() => { vi.advanceTimersByTime(2000) })
    }
    expect(FakeWebSocket.instances).toHaveLength(6) // original + 5 retries
  })

  it('does not retry after MAX_RETRIES exceeded', () => {
    renderHook(() => useWebSocket({ url: 'ws://test', onMessage: vi.fn() }))
    for (let i = 0; i < 5; i++) {
      act(() => { FakeWebSocket.latest.triggerClose() })
      act(() => { vi.advanceTimersByTime(2000) })
    }
    // 6th close — no more retries
    act(() => { FakeWebSocket.latest.triggerClose() })
    act(() => { vi.advanceTimersByTime(2000) })
    expect(FakeWebSocket.instances).toHaveLength(6)
  })

  it('resets retry count on successful reconnect', () => {
    renderHook(() => useWebSocket({ url: 'ws://test', onMessage: vi.fn() }))
    // First disconnect → retry 1
    act(() => { FakeWebSocket.latest.triggerClose() })
    act(() => { vi.advanceTimersByTime(2000) })
    // Reconnect succeeds → retry count reset to 0
    act(() => { FakeWebSocket.latest.triggerOpen() })
    // Second disconnect → should schedule a retry again (count is 1 now, well below MAX=5)
    act(() => { FakeWebSocket.latest.triggerClose() })
    act(() => { vi.advanceTimersByTime(2000) })
    expect(FakeWebSocket.instances).toHaveLength(3)
  })

  it('closes WebSocket and stops retries on unmount', () => {
    const { unmount } = renderHook(() => useWebSocket({ url: 'ws://test', onMessage: vi.fn() }))
    act(() => { FakeWebSocket.latest.triggerClose() })
    unmount()
    act(() => { vi.advanceTimersByTime(2000) })
    // No new instance after unmount
    expect(FakeWebSocket.instances).toHaveLength(1)
  })

  it('onerror triggers ws.close()', () => {
    renderHook(() => useWebSocket({ url: 'ws://test', onMessage: vi.fn() }))
    const ws = FakeWebSocket.latest
    act(() => { ws.triggerError() })
    expect(ws.close).toHaveBeenCalled()
  })

  it('send() sends serialized JSON when socket is OPEN', () => {
    const { result } = renderHook(() => useWebSocket({ url: 'ws://test', onMessage: vi.fn() }))
    act(() => { FakeWebSocket.latest.triggerOpen() })
    act(() => { result.current.send({ action: 'vote', targetId: 'p2' }) })
    expect(FakeWebSocket.latest.send).toHaveBeenCalledWith(
      JSON.stringify({ action: 'vote', targetId: 'p2' })
    )
  })

  it('send() is a no-op when socket is not OPEN', () => {
    const { result } = renderHook(() => useWebSocket({ url: 'ws://test', onMessage: vi.fn() }))
    // readyState is CONNECTING, not OPEN
    act(() => { result.current.send({ action: 'vote' }) })
    expect(FakeWebSocket.latest.send).not.toHaveBeenCalled()
  })

  it('reconnects when url changes', () => {
    const { rerender } = renderHook(
      ({ url }: { url: string }) => useWebSocket({ url, onMessage: vi.fn() }),
      { initialProps: { url: 'ws://test/old' } }
    )
    const first = FakeWebSocket.instances[0]
    rerender({ url: 'ws://test/new' })
    expect(first.close).toHaveBeenCalled()
    expect(FakeWebSocket.instances).toHaveLength(2)
    expect(FakeWebSocket.instances[1].url).toBe('ws://test/new')
  })
})
