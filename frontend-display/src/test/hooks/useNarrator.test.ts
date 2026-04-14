import { renderHook, act } from '@testing-library/react'
import { useNarrator } from '../../hooks/useNarrator'
import type { NarrateMessage } from '../../types/game'

function makeNarrateMsg(overrides: Partial<NarrateMessage> = {}): NarrateMessage {
  return {
    type: 'narrate',
    trigger: 'game_start',
    text: 'Night falls over the village.',
    audio_url: '/tts/audio/test.wav',
    duration_ms: 2000,
    phase: 'role_deal',
    round: 1,
    ...overrides,
  }
}

describe('useNarrator', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('sets narratorText after handleNarrate is called', () => {
    const { result } = renderHook(() => useNarrator())
    expect(result.current.narratorText).toBeNull()

    act(() => {
      result.current.handleNarrate(makeNarrateMsg({ text: 'hello' }))
    })

    expect(result.current.narratorText).toBe('hello')
  })

  it('creates an Audio element with the correct url and calls play()', () => {
    const mockPlay = vi.fn().mockResolvedValue(undefined)
    const mockAudioInstance = { play: mockPlay }
    const AudioConstructor = vi.fn(() => mockAudioInstance)
    vi.stubGlobal('Audio', AudioConstructor)

    const { result } = renderHook(() => useNarrator())
    act(() => {
      result.current.handleNarrate(makeNarrateMsg({ audio_url: '/tts/audio/hello.wav' }))
    })

    expect(AudioConstructor).toHaveBeenCalledWith('/tts/audio/hello.wav')
    expect(mockPlay).toHaveBeenCalledOnce()
  })

  it('clears narratorText after duration_ms elapses', () => {
    vi.stubGlobal('Audio', vi.fn(() => ({ play: vi.fn().mockResolvedValue(undefined) })))
    vi.useFakeTimers()
    const { result } = renderHook(() => useNarrator())

    act(() => {
      result.current.handleNarrate(makeNarrateMsg({ text: 'Night...', duration_ms: 1500 }))
    })
    expect(result.current.narratorText).toBe('Night...')

    act(() => {
      vi.advanceTimersByTime(1500)
    })
    expect(result.current.narratorText).toBeNull()
  })

  it('does not clear narratorText before duration_ms elapses', () => {
    vi.stubGlobal('Audio', vi.fn(() => ({ play: vi.fn().mockResolvedValue(undefined) })))
    vi.useFakeTimers()
    const { result } = renderHook(() => useNarrator())

    act(() => {
      result.current.handleNarrate(makeNarrateMsg({ text: 'Night...', duration_ms: 1500 }))
    })

    act(() => {
      vi.advanceTimersByTime(1000) // only partial elapsed
    })
    expect(result.current.narratorText).toBe('Night...')
  })

  it('swallows audio play() rejection without throwing', async () => {
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockRejectedValue(
      new DOMException('The play() request was interrupted', 'NotAllowedError'),
    )

    const { result } = renderHook(() => useNarrator())

    // Must not throw — the hook catches the rejection internally
    expect(() => {
      act(() => {
        result.current.handleNarrate(makeNarrateMsg())
      })
    }).not.toThrow()

    // Wait for the rejected promise to settle so it doesn't leak
    await vi.waitFor(() => {})
  })
})
