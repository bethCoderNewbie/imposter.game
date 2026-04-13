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

describe('useGameState (mobile)', () => {
  beforeEach(() => {
    capturedOnMessage = () => {}
    capturedOnStatusChange = undefined
  })

  it('has null gameState and "closed" status initially', () => {
    const { result } = renderHook(() =>
      useGameState({ gameId: 'abc', playerId: 'p1', sessionToken: 'tok' })
    )
    expect(result.current.gameState).toBeNull()
    expect(result.current.status).toBe('closed')
  })

  it('updates gameState on sync message (ADR-011 Decision 1)', () => {
    const { result } = renderHook(() =>
      useGameState({ gameId: 'g1', playerId: 'p1' })
    )
    const state = makeGameState({ phase: 'lobby' })
    act(() => {
      capturedOnMessage({ type: 'sync', state_id: 1, schema_version: '0.4', state })
    })
    expect(result.current.gameState?.phase).toBe('lobby')
  })

  it('updates gameState on update message (ADR-011 Decision 1)', () => {
    const { result } = renderHook(() =>
      useGameState({ gameId: 'g1', playerId: 'p1' })
    )
    const state = makeGameState({ phase: 'night' })
    act(() => {
      capturedOnMessage({ type: 'update', state_id: 1, schema_version: '0.4', state })
    })
    expect(result.current.gameState?.phase).toBe('night')
  })

  it('ignores update with stale state_id', () => {
    const { result } = renderHook(() =>
      useGameState({ gameId: 'g1', playerId: 'p1' })
    )
    const stateNight = makeGameState({ phase: 'night' })
    const stateLobby = makeGameState({ phase: 'lobby' })
    act(() => {
      capturedOnMessage({ type: 'update', state_id: 5, schema_version: '0.4', state: stateNight })
    })
    act(() => {
      capturedOnMessage({ type: 'update', state_id: 3, schema_version: '0.4', state: stateLobby })
    })
    expect(result.current.gameState?.phase).toBe('night')
  })

  it('calls onHint callback on hint_reward message', () => {
    const onHint = vi.fn()
    renderHook(() =>
      useGameState({ gameId: 'g1', playerId: 'p1', onHint })
    )
    const hint = {
      type: 'hint_reward',
      hint_id: 'h1',
      category: 'logic',
      text: 'The seer is suspicious.',
      round: 1,
      expires_after_round: null,
    }
    act(() => { capturedOnMessage(hint) })
    expect(onHint).toHaveBeenCalledWith(hint)
  })

  it('logs console.warn on error message', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { result } = renderHook(() =>
      useGameState({ gameId: 'g1', playerId: 'p1' })
    )
    act(() => {
      capturedOnMessage({ type: 'error', code: 'DEAD_PLAYER_ACTION', message: 'You are dead.' })
    })
    expect(result.current.gameState).toBeNull()
    expect(warnSpy).toHaveBeenCalledWith('[WS error]', 'DEAD_PLAYER_ACTION', 'You are dead.')
    warnSpy.mockRestore()
  })

  it('silently ignores old state_update message type (pre-ADR-011 regression guard)', () => {
    const { result } = renderHook(() =>
      useGameState({ gameId: 'g1', playerId: 'p1' })
    )
    const state = makeGameState({ phase: 'day' })
    act(() => {
      capturedOnMessage({ type: 'state_update', state_id: 1, state })
    })
    // gameState must remain null — old message type is not recognized
    expect(result.current.gameState).toBeNull()
  })

  it('sendIntent delegates to send from useWebSocket', () => {
    const { result } = renderHook(() =>
      useGameState({ gameId: 'g1', playerId: 'p1' })
    )
    act(() => {
      result.current.sendIntent({ type: 'submit_day_vote', target_id: 'p2' })
    })
    expect(mockSend).toHaveBeenCalledWith({ type: 'submit_day_vote', target_id: 'p2' })
  })

  it('propagates WsStatus changes via onStatusChange', () => {
    const { result } = renderHook(() =>
      useGameState({ gameId: 'g1', playerId: 'p1' })
    )
    act(() => { capturedOnStatusChange?.('open') })
    expect(result.current.status).toBe('open')
  })

  // ── Rematch redirect: state-id fence must reset on game switch ───────────────

  it('resets gameState to null when gameId changes (redirect fence reset)', async () => {
    const { result, rerender } = renderHook(
      ({ gameId, playerId }: { gameId: string; playerId: string }) =>
        useGameState({ gameId, playerId }),
      { initialProps: { gameId: 'old-game', playerId: 'old-pid' } },
    )
    act(() => {
      capturedOnMessage({ type: 'sync', state_id: 80, schema_version: '0.4', state: makeGameState({ phase: 'game_over' }) })
    })
    expect(result.current.gameState?.phase).toBe('game_over')

    rerender({ gameId: 'new-game', playerId: 'new-pid' })
    expect(result.current.gameState).toBeNull()
  })

  it('accepts low state_id from new game after redirect (rematch scenario)', async () => {
    const { result, rerender } = renderHook(
      ({ gameId, playerId }: { gameId: string; playerId: string }) =>
        useGameState({ gameId, playerId }),
      { initialProps: { gameId: 'old-game', playerId: 'old-pid' } },
    )
    // Old game ends at a high state_id
    act(() => {
      capturedOnMessage({ type: 'sync', state_id: 80, schema_version: '0.4', state: makeGameState({ phase: 'game_over' }) })
    })

    // Redirect fires — new game/player IDs from handleRedirect in App.tsx
    rerender({ gameId: 'new-game', playerId: 'new-pid' })

    // New game sends state_id=1 — must NOT be blocked by the stale fence
    act(() => {
      capturedOnMessage({ type: 'sync', state_id: 1, schema_version: '0.4', state: makeGameState({ phase: 'lobby' }) })
    })
    expect(result.current.gameState?.phase).toBe('lobby')
  })
})
