import './AttackWarningOverlay.css'

interface Props {
  sendIntent: (payload: Record<string, unknown>) => void
}

/** Minimal attack warning — just a Defend button.
 * Deliberately understated so other players nearby don't notice.
 * No haptics, no red screen — secrecy constraint (PRD-002 §3.4). */
export default function AttackWarningOverlay({ sendIntent }: Props) {
  return (
    <div className="attack-overlay" aria-live="polite" aria-label="Defend">
      <button
        className="attack-overlay__defend-btn"
        onClick={() => sendIntent({ type: 'grid_defend' })}
      >
        DEFEND
      </button>
    </div>
  )
}
