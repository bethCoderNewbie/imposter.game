import { renderHook, act } from '@testing-library/react'
import { useTimer } from '../../hooks/useTimer'

// ── RAF stub helpers ─────────────────────────────────────────────────────────

type RafCallback = FrameRequestCallback
let rafCallbacks: RafCallback[] = []
let rafId = 0
let cancelledIds: number[] = []

function setupRafStub() {
  rafCallbacks = []
  cancelledIds = []
  rafId = 0
  vi.stubGlobal('requestAnimationFrame', vi.fn((cb: RafCallback) => {
    rafCallbacks.push(cb)
    return ++rafId
  }))
  vi.stubGlobal('cancelAnimationFrame', vi.fn((id: number) => {
    cancelledIds.push(id)
    rafCallbacks = rafCallbacks.filter((_, i) => i !== id - 1)
  }))
}

function flushRaf() {
  const pending = rafCallbacks.slice()
  rafCallbacks = []
  pending.forEach(cb => cb(performance.now()))
}

// ── Setup / teardown ─────────────────────────────────────────────────────────

beforeEach(() => {
  vi.useFakeTimers()
  setupRafStub()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

// ── Helpers ───────────────────────────────────────────────────────────────────

/** ISO string `n` seconds from the fake-timer "now" */
function futureIso(seconds: number): string {
  return new Date(Date.now() + seconds * 1000).toISOString()
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('useTimer', () => {
  it('returns 0 seconds and no warning/critical when timerEndsAt is null', () => {
    const { result } = renderHook(() => useTimer(null))
    expect(result.current.secondsRemaining).toBe(0)
    expect(result.current.isWarning).toBe(false)
    expect(result.current.isCritical).toBe(false)
  })

  it('returns correct seconds on first RAF tick', () => {
    const { result } = renderHook(() => useTimer(futureIso(90)))
    act(() => { flushRaf() })
    expect(result.current.secondsRemaining).toBe(90)
  })

  it('isWarning is true when 1–30 seconds remain', () => {
    const { result } = renderHook(() => useTimer(futureIso(25)))
    act(() => { flushRaf() })
    expect(result.current.isWarning).toBe(true)
    expect(result.current.isCritical).toBe(false)
  })

  it('isCritical is true when 1–10 seconds remain', () => {
    const { result } = renderHook(() => useTimer(futureIso(5)))
    act(() => { flushRaf() })
    expect(result.current.isCritical).toBe(true)
    expect(result.current.isWarning).toBe(true)
  })

  it('clamps to 0 when timer has already expired', () => {
    vi.setSystemTime(Date.now() + 20 * 1000) // advance clock 20s
    const { result } = renderHook(() => useTimer(futureIso(-5))) // 5s in past
    act(() => { flushRaf() })
    expect(result.current.secondsRemaining).toBe(0)
    expect(result.current.isWarning).toBe(false)
  })

  it('cancels animation frame on unmount', () => {
    const { unmount } = renderHook(() => useTimer(futureIso(60)))
    act(() => { flushRaf() }) // triggers next RAF scheduling
    unmount()
    expect(vi.mocked(cancelAnimationFrame)).toHaveBeenCalled()
  })

  it('updates when timerEndsAt changes from null to a value', () => {
    const { result, rerender } = renderHook(
      ({ t }: { t: string | null }) => useTimer(t),
      { initialProps: { t: null } }
    )
    expect(result.current.secondsRemaining).toBe(0)
    rerender({ t: futureIso(45) })
    act(() => { flushRaf() })
    expect(result.current.secondsRemaining).toBe(45)
  })

  it('stops scheduling RAF frames once remaining hits 0', () => {
    vi.setSystemTime(Date.now() + 100 * 1000) // way in the future
    const { result } = renderHook(() => useTimer(futureIso(-50))) // already expired
    act(() => { flushRaf() })
    const countAfterExpiry = (vi.mocked(requestAnimationFrame) as ReturnType<typeof vi.fn>).mock.calls.length
    act(() => { flushRaf() })
    // No additional RAF calls after expiry
    expect((vi.mocked(requestAnimationFrame) as ReturnType<typeof vi.fn>).mock.calls.length)
      .toBe(countAfterExpiry)
    expect(result.current.secondsRemaining).toBe(0)
  })
})
