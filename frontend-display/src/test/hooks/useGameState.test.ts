import { renderHook, act } from '@testing-library/react'
import type { WsStatus } from '../../hooks/useWebSocket'
import { useGameState } from '../../hooks/useGameState'
import { useGameStore } from '../../store/gameStore'
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
    useGameStore.setState({ roster: [] })
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

  it('updates gameState on sync message', () => {
    const { result } = renderHook(() =>
      useGameState({ gameId: 'g1', playerId: 'display' })
    )
    const state = makeGameState({ phase: 'lobby' })
    act(() => {
      capturedOnMessage({ type: 'sync', state_id: 1, schema_version: '1', state })
    })
    expect(result.current.gameState?.phase).toBe('lobby')
  })

  it('ignores update with stale state_id', () => {
    const { result } = renderHook(() =>
      useGameState({ gameId: 'g1', playerId: 'display' })
    )
    const state5 = makeGameState({ phase: 'night' })
    const state3 = makeGameState({ phase: 'lobby' })
    act(() => {
      capturedOnMessage({ type: 'update', state_id: 5, schema_version: '1', state: state5 })
    })
    act(() => {
      capturedOnMessage({ type: 'update', state_id: 3, schema_version: '1', state: state3 })
    })
    // state3 is older — should keep state5's phase
    expect(result.current.gameState?.phase).toBe('night')
  })

  it('applies sequential updates in order', () => {
    const { result } = renderHook(() =>
      useGameState({ gameId: 'g1', playerId: 'display' })
    )
    act(() => {
      capturedOnMessage({ type: 'sync', state_id: 1, schema_version: '1', state: makeGameState({ phase: 'lobby' }) })
    })
    act(() => {
      capturedOnMessage({ type: 'update', state_id: 2, schema_version: '1', state: makeGameState({ phase: 'night' }) })
    })
    expect(result.current.gameState?.phase).toBe('night')
  })

  it('match_data dispatches roster to Zustand store', () => {
    renderHook(() => useGameState({ gameId: 'g1', playerId: 'display' }))
    const roster = [{ player_id: 'p1', display_name: 'Alice', avatar_id: 'avatar_01', is_connected: true }]
    act(() => {
      capturedOnMessage({ type: 'match_data', players: roster })
    })
    expect(useGameStore.getState().roster).toEqual(roster)
  })

  it('sync seeds roster from state.players', () => {
    const state = makeGameState({ phase: 'lobby' })
    renderHook(() => useGameState({ gameId: 'g1', playerId: 'display' }))
    act(() => {
      capturedOnMessage({ type: 'sync', state_id: 1, schema_version: '1', state })
    })
    expect(useGameStore.getState().roster.length).toBe(Object.keys(state.players).length)
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

  // ── gameId-change reset (rematch / new-match bug) ───────────────────────────

  it('resets gameState to null when gameId changes', async () => {
    const { result, rerender } = renderHook(
      ({ gameId }: { gameId: string | null }) =>
        useGameState({ gameId, playerId: 'display' }),
      { initialProps: { gameId: 'game-1' } },
    )
    act(() => {
      capturedOnMessage({ type: 'sync', state_id: 50, schema_version: '1', state: makeGameState({ phase: 'game_over' }) })
    })
    expect(result.current.gameState?.phase).toBe('game_over')

    rerender({ gameId: 'game-2' })
    expect(result.current.gameState).toBeNull()
  })

  it('accepts low state_id from new game after gameId change', async () => {
    const { result, rerender } = renderHook(
      ({ gameId }: { gameId: string | null }) =>
        useGameState({ gameId, playerId: 'display' }),
      { initialProps: { gameId: 'game-1' } },
    )
    // Old game ends at state_id=100
    act(() => {
      capturedOnMessage({ type: 'sync', state_id: 100, schema_version: '1', state: makeGameState({ phase: 'game_over' }) })
    })

    // Switch to new game
    rerender({ gameId: 'game-2' })

    // New game sends state_id=1 — must NOT be dropped by the stale fence
    act(() => {
      capturedOnMessage({ type: 'sync', state_id: 1, schema_version: '1', state: makeGameState({ phase: 'lobby' }) })
    })
    expect(result.current.gameState?.phase).toBe('lobby')
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
