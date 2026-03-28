import { useTimer } from '../../hooks/useTimer'
import './PhaseTimer.css'

interface Props {
  timerEndsAt: string | null
  className?: string
}

export default function PhaseTimer({ timerEndsAt, className }: Props) {
  const { secondsRemaining, isWarning, isCritical } = useTimer(timerEndsAt)
  const mm = String(Math.floor(secondsRemaining / 60)).padStart(2, '0')
  const ss = String(secondsRemaining % 60).padStart(2, '0')
  const stateClass = isCritical ? 'timer--critical' : isWarning ? 'timer--warning' : ''
  return (
    <span className={['phase-timer', stateClass, className].filter(Boolean).join(' ')}>
      {mm}:{ss}
    </span>
  )
}
