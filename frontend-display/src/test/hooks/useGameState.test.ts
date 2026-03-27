import { renderHook, act } from '@testing-library/react'
import type { WsStatus } from '../../hooks/useWebSocket'
import { useGameState } from '../../hooks/useGameState'
import { makeGameState } from '../fixtures'

// ── Mock useWebSocket ─────────────────────────────────────────────────────────

let capturedOnMessage: (data: unknown) => void = () => {}
let capturedOnStatusChange: ((s: WsStatus) => void) | undefined
let mockSend: ReturnType<typeof vi.fn>

vi.mock('../../hooks/useWebSocket', () => ({
  useWebSocket: vi.fn((opts: {
    url: string | null
    onMessage: (d: unknown) => void
    onStatusChange?: (s: WsStatus) => void
    sessionToken?: string
  }) => {
    capturedOnMessage = opts.onMessage
    capturedOnStatusChange = opts.onStatusChange
    mockSend = vi.fn()
    return { send: mockSend }
  }),
}))

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('useGameState', () => {
  beforeEach(() => {
    capturedOnMessage = () => {}
    capturedOnStatusChange = undefined
  })

  it('has null gameState and "closed" status initially', () => {
    const { result } = renderHook(() =>
      useGameState({ gameId: 'abc', playerId: 'display' })
    )
    expect(result.current.gameState).toBeNull()
    expect(result.current.status).toBe('closed')
  })

  it('passes null url to useWebSocket when gameId is null', async () => {
    const { useWebSocket } = await import('../../hooks/useWebSocket')
    renderHook(() => useGameState({ gameId: null, playerId: 'display' }))
    expect(vi.mocked(useWebSocket)).toHaveBeenCalledWith(
      expect.objectContaining({ url: null })
    )
  })

  it('builds ws url from gameId and playerId', async () => {
    const { useWebSocket } = await import('../../hooks/useWebSocket')
    renderHook(() => useGameState({ gameId: 'game-1', playerId: 'display' }))
    const callArg = vi.mocked(useWebSocket).mock.calls.at(-1)![0]
    expect(callArg.url).toMatch(/\/ws\/game-1\/display$/)
  })

  it('updates gameState on state_update message', () => {
    const { result } = renderHook(() =>
      useGameState({ gameId: 'g1', playerId: 'display' })
    )
    const state = makeGameState({ phase: 'lobby' })
    act(() => {
      capturedOnMessage({ type: 'state_update', state_id: 1, state })
    })
    expect(result.current.gameState?.phase).toBe('lobby')
  })

  it('ignores state_update with stale state_id', () => {
    const { result } = renderHook(() =>
      useGameState({ gameId: 'g1', playerId: 'display' })
    )
    const state5 = makeGameState({ phase: 'night' })
    const state3 = makeGameState({ phase: 'lobby' })
    act(() => {
      capturedOnMessage({ type: 'state_update', state_id: 5, state: state5 })
    })
    act(() => {
      capturedOnMessage({ type: 'state_update', state_id: 3, state: state3 })
    })
    // state3 is older — should keep state5's phase
    expect(result.current.gameState?.phase).toBe('night')
  })

  it('applies sequential state_updates in order', () => {
    const { result } = renderHook(() =>
      useGameState({ gameId: 'g1', playerId: 'display' })
    )
    act(() => {
      capturedOnMessage({ type: 'state_update', state_id: 1, state: makeGameState({ phase: 'lobby' }) })
    })
    act(() => {
      capturedOnMessage({ type: 'state_update', state_id: 2, state: makeGameState({ phase: 'night' }) })
    })
    expect(result.current.gameState?.phase).toBe('night')
  })

  it('logs warning on error message and does not change gameState', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { result } = renderHook(() =>
      useGameState({ gameId: 'g1', playerId: 'display' })
    )
    act(() => {
      capturedOnMessage({ type: 'error', code: 'FORBIDDEN', message: 'Not allowed' })
    })
    expect(result.current.gameState).toBeNull()
    expect(warnSpy).toHaveBeenCalledWith('[WS error]', 'FORBIDDEN', 'Not allowed')
    warnSpy.mockRestore()
  })

  it('sendIntent delegates to send from useWebSocket', () => {
    const { result } = renderHook(() =>
      useGameState({ gameId: 'g1', playerId: 'display' })
    )
    act(() => {
      result.current.sendIntent({ type: 'vote', targetId: 'p3' })
    })
    expect(mockSend).toHaveBeenCalledWith({ type: 'vote', targetId: 'p3' })
  })

  it('uses wss: protocol when window.location.protocol is https:', async () => {
    const { useWebSocket } = await import('../../hooks/useWebSocket')
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { protocol: 'https:', host: 'example.com' },
    })
    renderHook(() => useGameState({ gameId: 'g1', playerId: 'display' }))
    const callArg = vi.mocked(useWebSocket).mock.calls.at(-1)![0]
    expect(callArg.url).toMatch(/^wss:\/\//)
    // Restore default
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { protocol: 'http:', host: 'localhost' },
    })
  })
})
