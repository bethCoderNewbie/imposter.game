import { useState, useCallback } from 'react'
import type { NarrateMessage } from '../types/game'

export function useNarrator() {
  const [narratorText, setNarratorText] = useState<string | null>(null)

  const handleNarrate = useCallback((msg: NarrateMessage) => {
    // Play audio — the browser audio context is already unlocked by App.tsx click-to-begin
    const audio = new Audio(msg.audio_url)
    audio.play().catch(() => {
      // Ignore play() failures (e.g. unsupported format, network error)
    })

    // Show subtitle and auto-clear after the WAV duration
    setNarratorText(msg.text)
    setTimeout(() => setNarratorText(null), msg.duration_ms)
  }, [])

  return { narratorText, handleNarrate }
}
