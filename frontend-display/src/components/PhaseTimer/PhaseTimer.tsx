import { useTimer } from '../../hooks/useTimer'
import { useCountdownBeep } from '../../hooks/useCountdownBeep'
import './PhaseTimer.css'

interface Props {
  timerEndsAt: string | null
  className?: string
  /** Enable per-second beep for the final 10s (PRD-012 §2.1) */
  enableCountdownBeep?: boolean
  audioUnlocked?: boolean
}

export default function PhaseTimer({ timerEndsAt, className, enableCountdownBeep, audioUnlocked }: Props) {
  const { secondsRemaining, isWarning, isCritical } = useTimer(timerEndsAt)
  useCountdownBeep(secondsRemaining, !!(enableCountdownBeep && audioUnlocked))
  const mm = String(Math.floor(secondsRemaining / 60)).padStart(2, '0')
  const ss = String(secondsRemaining % 60).padStart(2, '0')
  const stateClass = isCritical ? 'timer--critical' : isWarning ? 'timer--warning' : ''
  return (
    <span className={['phase-timer', stateClass, className].filter(Boolean).join(' ')}>
      {mm}:{ss}
    </span>
  )
}
