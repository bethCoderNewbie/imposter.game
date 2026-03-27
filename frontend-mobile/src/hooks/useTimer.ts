import { useState, useEffect, useRef } from 'react'

export function useTimer(timerEndsAt: string | null) {
  const [secondsRemaining, setSecondsRemaining] = useState(0)
  const rafRef = useRef<number | null>(null)

  useEffect(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }

    if (!timerEndsAt) {
      setSecondsRemaining(0)
      return
    }

    const endTime = new Date(timerEndsAt).getTime()

    function tick() {
      const remaining = Math.max(0, Math.ceil((endTime - Date.now()) / 1000))
      setSecondsRemaining(remaining)
      if (remaining > 0) {
        rafRef.current = requestAnimationFrame(tick)
      }
    }

    rafRef.current = requestAnimationFrame(tick)

    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    }
  }, [timerEndsAt])

  return {
    secondsRemaining,
    isWarning: secondsRemaining > 0 && secondsRemaining <= 30,
    isCritical: secondsRemaining > 0 && secondsRemaining <= 10,
  }
}
