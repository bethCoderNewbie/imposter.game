import { useEffect, useRef } from 'react'
import { useHaptics } from '../../hooks/useHaptics'
import type { HintPayload, PlayerState } from '../../types/game'
import PuzzleRenderer from './PuzzleRenderer'
import './ActionUI.css'

interface Props {
  myPlayer: PlayerState
  sendIntent: (payload: Record<string, unknown>) => void
  latestHint?: HintPayload | null
}

/** Archive puzzle UI for wakeOrder==0 players (Villager, Mayor, Jester).
 *  Anti-cheat: same dark panel silhouette as wolf-vote screen (PRD-002 §3.4).
 *  Puzzle data comes from myPlayer.puzzle_state — correct_index stripped server-side. */
export default function VillagerDecoyUI({ myPlayer, sendIntent, latestHint }: Props) {
  const puzzle = myPlayer.puzzle_state ?? null
  const { vibrate } = useHaptics()

  // Haptic feedback on Archive solve
  const hasFired = useRef(false)
  useEffect(() => {
    if (puzzle?.solved && !hasFired.current) {
      hasFired.current = true
      vibrate(100)
    }
  }, [puzzle?.solved]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!puzzle) {
    return (
      <div className="action-ui action-ui--centered">
        <p className="action-ui__header">The Archives await…</p>
      </div>
    )
  }

  return (
    <PuzzleRenderer
      puzzle={puzzle}
      sendIntent={sendIntent}
      latestHint={latestHint}
      source="archive"
    />
  )
}
