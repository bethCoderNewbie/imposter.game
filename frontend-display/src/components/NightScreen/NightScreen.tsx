import { useEffect, useRef, useState } from 'react'
import { useTimer } from '../../hooks/useTimer'
import type { StrippedGameState } from '../../types/game'
import './NightScreen.css'

const NARRATIVES = [
  'The village sleeps…',
  'Something stirs in the dark…',
  'The Werewolves are hunting…',
  'The Seer peers into the shadows…',
  'A guardian watches over the village…',
]

interface Props {
  gameState: StrippedGameState
  audioUnlocked: boolean
}

export default function NightScreen({ gameState, audioUnlocked }: Props) {
  const { secondsRemaining, isWarning, isCritical } = useTimer(gameState.timer_ends_at)
  const [narrativeIdx, setNarrativeIdx] = useState(0)
  const ambientRef = useRef<HTMLAudioElement>(null)

  // Rotate narrative text every 8s (PRD-002 §2.3)
  useEffect(() => {
    const interval = setInterval(() => {
      setNarrativeIdx(i => (i + 1) % NARRATIVES.length)
    }, 8000)
    return () => clearInterval(interval)
  }, [])

  // Play ambient audio when unlocked (HTML5 audio — ADR-003 §3)
  // Audio files are expected at /audio/night-ambient.mp3
  useEffect(() => {
    if (audioUnlocked && ambientRef.current) {
      ambientRef.current.volume = 0.4
      ambientRef.current.play().catch(() => {/* silently ignored if no file */})
    }
    return () => {
      ambientRef.current?.pause()
    }
  }, [audioUnlocked])

  const mm = String(Math.floor(secondsRemaining / 60)).padStart(2, '0')
  const ss = String(secondsRemaining % 60).padStart(2, '0')

  const timerClass = isCritical ? 'timer--critical' : isWarning ? 'timer--warning' : ''

  const { actions_submitted_count, actions_required_count } = gameState.night_actions

  return (
    <div className="night-screen">
      {/* Preloaded audio — plays on phase enter */}
      <audio ref={ambientRef} src="/audio/night-ambient.mp3" loop preload="auto" />

      {/* Moon illustration */}
      <div className="night-screen__moon" aria-hidden="true">🌕</div>

      {/* Countdown timer — PRD-003 §2.2 */}
      <div className={`night-screen__timer ${timerClass}`}>
        {mm}:{ss}
      </div>

      {/* Atmospheric narrative carousel — PRD-002 §2.3 */}
      <p className="night-screen__narrative" key={narrativeIdx}>
        {NARRATIVES[narrativeIdx]}
      </p>

      {/* Action progress — PRD-002 §2.3 */}
      <div className="night-screen__progress">
        Night actions: {actions_submitted_count} / {actions_required_count}
      </div>
    </div>
  )
}
