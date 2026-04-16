import { useTimer } from '../../hooks/useTimer'
import { useCountdownBeep } from '../../hooks/useCountdownBeep'
import './PhaseTimer.css'

interface Props {
  timerEndsAt: string | null
  timerPaused?: boolean
  timerRemainingSeconds?: number | null
  className?: string
  /** Enable per-second beep for the final 10s (PRD-012 §2.1) */
  enableCountdownBeep?: boolean
  audioUnlocked?: boolean
}

export default function PhaseTimer({
  timerEndsAt, timerPaused, timerRemainingSeconds,
  className, enableCountdownBeep, audioUnlocked,
}: Props) {
  const { secondsRemaining: liveSeconds, isWarning, isCritical } = useTimer(timerEndsAt)
  useCountdownBeep(liveSeconds, !!(enableCountdownBeep && audioUnlocked && !timerPaused))

  const displaySeconds = timerPaused ? (timerRemainingSeconds ?? liveSeconds) : liveSeconds
  const mm = String(Math.floor(displaySeconds / 60)).padStart(2, '0')
  const ss = String(displaySeconds % 60).padStart(2, '0')
  const stateClass = timerPaused ? 'timer--paused'
    : isCritical ? 'timer--critical'
    : isWarning ? 'timer--warning' : ''

  return (
    <span className={['phase-timer', stateClass, className].filter(Boolean).join(' ')}>
      {timerPaused && <span className="phase-timer__paused-label">PAUSED </span>}
      {mm}:{ss}
    </span>
  )
}
