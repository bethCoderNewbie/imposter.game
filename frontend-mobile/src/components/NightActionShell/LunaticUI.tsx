import { useHaptics } from '../../hooks/useHaptics'
import type { PlayerState } from '../../types/game'
import './ActionUI.css'

interface Props {
  myPlayer: PlayerState
  sendIntent: (payload: Record<string, unknown>) => void
}

export default function LunaticUI({ myPlayer, sendIntent }: Props) {
  const redirectUsed = myPlayer.lunatic_redirect_used ?? false
  const { vibrate } = useHaptics()

  function handleRedirect() {
    vibrate(300)
    sendIntent({ type: 'submit_night_action', lunatic_action: 'redirect' })
  }

  function handleSkip() {
    vibrate(100)
    sendIntent({ type: 'submit_night_action', lunatic_action: 'skip' })
  }

  if (redirectUsed) {
    return <p className="action-ui__header">Your sacrifice has been used.</p>
  }

  return (
    <div className="action-ui">
      <p className="action-ui__header">The wolves hunt tonight…</p>
      <button className="action-ui__confirm" onClick={handleRedirect}>
        Redirect kill to yourself
      </button>
      <button className="action-ui__confirm" onClick={handleSkip}>
        Do nothing tonight
      </button>
    </div>
  )
}
