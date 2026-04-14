import { useRef, useEffect } from 'react'

/**
 * Plays a synthetic beep each second when `secondsRemaining` is in the
 * range [1, 10] and `isActive` is true (PRD-012 §2.1, ADR-023).
 *
 * Uses Web Audio API — no MP3 asset required.
 * The final second (1) fires at 880 Hz; all others at 440 Hz.
 */
export function useCountdownBeep(secondsRemaining: number, isActive: boolean) {
  const prevSecondsRef = useRef<number | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)

  useEffect(() => {
    if (!isActive || secondsRemaining > 10 || secondsRemaining <= 0) {
      prevSecondsRef.current = null
      return
    }
    // Fire once per unique second value — useTimer uses rAF so this effect
    // may re-run multiple times with the same integer value.
    if (prevSecondsRef.current === secondsRemaining) return
    prevSecondsRef.current = secondsRemaining

    // Lazy-init AudioContext (must happen after a user gesture — guaranteed
    // by the audioUnlocked gate in App.tsx).
    audioCtxRef.current ??= new AudioContext()
    const ctx = audioCtxRef.current

    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.connect(gain)
    gain.connect(ctx.destination)

    osc.frequency.value = secondsRemaining === 1 ? 880 : 440
    osc.type = 'sine'

    const now = ctx.currentTime
    gain.gain.setValueAtTime(0.3, now)
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.12)
    osc.start(now)
    osc.stop(now + 0.12)
  }, [secondsRemaining, isActive])
}
