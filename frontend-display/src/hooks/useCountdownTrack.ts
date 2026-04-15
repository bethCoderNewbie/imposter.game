import { useRef, useEffect } from 'react'

/**
 * Plays a countdown MP3 track once per phase when `secondsRemaining` first
 * drops to `threshold` (default 10).
 *
 * Keyed on `timerEndsAt` so the track fires exactly once per phase and resets
 * automatically when the phase changes.
 */
export function useCountdownTrack(
  secondsRemaining: number,
  timerEndsAt: string | null,
  isActive: boolean,
  trackUrl: string,
  threshold = 10,
) {
  const firedForRef = useRef<string | null>(null)
  const audioRef    = useRef<HTMLAudioElement | null>(null)

  // Clean up audio and reset fire-guard when the phase timer changes
  useEffect(() => {
    firedForRef.current = null
    return () => {
      audioRef.current?.pause()
      audioRef.current = null
    }
  }, [timerEndsAt])

  useEffect(() => {
    if (!isActive) return
    if (secondsRemaining <= 0 || secondsRemaining > threshold) return
    if (firedForRef.current === timerEndsAt) return   // already played this phase

    firedForRef.current = timerEndsAt
    const audio = new Audio(trackUrl)
    audio.volume = 0.55
    audioRef.current = audio
    audio.play().catch(() => {})
  }, [secondsRemaining, isActive, timerEndsAt, trackUrl, threshold])
}
