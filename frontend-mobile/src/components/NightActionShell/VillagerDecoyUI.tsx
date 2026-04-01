import { useEffect, useRef, useState } from 'react'
import { useHaptics } from '../../hooks/useHaptics'
import type { HintPayload, PlayerState, PuzzleState } from '../../types/game'
import './ActionUI.css'

// How long to keep buttons locked after a click before re-enabling (safety valve
// for WRONG_PHASE / network error when no state update arrives).
const LOCK_TIMEOUT_MS = 4000

interface Props {
  myPlayer: PlayerState
  sendIntent: (payload: Record<string, unknown>) => void
  latestHint?: HintPayload | null
}

/** Archive puzzle UI for wakeOrder==0 players (Villager, Mayor, Jester).
 *  Anti-cheat: same dark panel silhouette as wolf-vote screen (PRD-002 §3.4, archivePuzzleSystem.antiCheatConstraint).
 *  Puzzle data comes from gameState.night_actions.puzzle_state — correct_index stripped server-side. */
export default function VillagerDecoyUI({ myPlayer, sendIntent, latestHint }: Props) {
  const puzzle = myPlayer.puzzle_state ?? null
  const { vibrate } = useHaptics()

  if (!puzzle) {
    return (
      <div className="action-ui action-ui--centered">
        <p className="action-ui__header">The Archives await…</p>
      </div>
    )
  }

  if (puzzle.active) {
    return (
      <ActivePuzzle
        puzzle={puzzle}
        sendIntent={sendIntent}
      />
    )
  }

  // Puzzle resolved
  return (
    <ResolvedPuzzle
      puzzle={puzzle}
      latestHint={latestHint}
      vibrate={vibrate}
    />
  )
}

// ── Active puzzle ─────────────────────────────────────────────────────────────

interface ActiveProps {
  puzzle: PuzzleState
  sendIntent: (payload: Record<string, unknown>) => void
}

function ActivePuzzle({ puzzle, sendIntent }: ActiveProps) {
  const startRef = useRef(Date.now())
  const [pct, setPct] = useState(100)
  const rafRef = useRef<number>(0)

  useEffect(() => {
    startRef.current = Date.now()
    const tick = () => {
      const elapsed = (Date.now() - startRef.current) / 1000
      const remaining = Math.max(0, puzzle.time_limit_seconds - elapsed)
      setPct((remaining / puzzle.time_limit_seconds) * 100)
      if (remaining > 0) rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [puzzle.time_limit_seconds])

  const isWarning = pct < (8 / puzzle.time_limit_seconds) * 100

  if (puzzle.puzzle_type === 'sequence') {
    return <SequencePuzzle puzzle={puzzle} sendIntent={sendIntent} pct={pct} isWarning={isWarning} />
  }

  return <ChoicePuzzle puzzle={puzzle} sendIntent={sendIntent} pct={pct} isWarning={isWarning} />
}

// ── Multiple-choice puzzle (logic + math) ─────────────────────────────────────

interface ChoiceProps {
  puzzle: PuzzleState
  sendIntent: (payload: Record<string, unknown>) => void
  pct: number
  isWarning: boolean
}

function ChoicePuzzle({ puzzle, sendIntent, pct, isWarning }: ChoiceProps) {
  const data = puzzle.puzzle_data as { question?: string; expression?: string; answer_options: string[] }
  const prompt = data.question ?? data.expression ?? ''
  const options = data.answer_options ?? []
  const [locked, setLocked] = useState(false)
  const unlockTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  function handleAnswer(i: number) {
    if (locked) return
    setLocked(true)
    sendIntent({ type: 'submit_puzzle_answer', answer_index: i })
    // Re-enable after timeout in case the server rejects (e.g. WRONG_PHASE)
    unlockTimer.current = setTimeout(() => setLocked(false), LOCK_TIMEOUT_MS)
  }

  useEffect(() => () => {
    if (unlockTimer.current) clearTimeout(unlockTimer.current)
  }, [])

  return (
    <div className="action-ui">
      <p className="action-ui__header">The Archives await. Solve the puzzle to earn a clue.</p>
      <div className="action-ui__timer-bar-track">
        <div
          className={`action-ui__timer-bar${isWarning ? ' action-ui__timer-bar--warning' : ''}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="action-ui__puzzle-panel">
        <p className="action-ui__puzzle-question">{prompt}</p>
        <div className="action-ui__answer-grid">
          {options.map((opt, i) => (
            <button
              key={i}
              className="action-ui__answer-btn"
              disabled={locked}
              onClick={() => handleAnswer(i)}
            >
              {opt}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Sequence puzzle (Simon Says) ──────────────────────────────────────────────

const TILE_COLORS: Record<string, string> = {
  red: '#e53e3e',
  blue: '#3182ce',
  green: '#38a169',
  yellow: '#d69e2e',
}

interface SequenceProps {
  puzzle: PuzzleState
  sendIntent: (payload: Record<string, unknown>) => void
  pct: number
  isWarning: boolean
}

function SequencePuzzle({ puzzle, sendIntent, pct, isWarning }: SequenceProps) {
  const data = puzzle.puzzle_data as { sequence: string[] }
  const sequence = data.sequence ?? []
  const [flashIdx, setFlashIdx] = useState<number | null>(null)
  const [showing, setShowing] = useState(true)  // true = flashing sequence; false = player input
  const [playerInput, setPlayerInput] = useState<string[]>([])
  const [locked, setLocked] = useState(false)
  const unlockTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => () => {
    if (unlockTimer.current) clearTimeout(unlockTimer.current)
  }, [])

  // Flash the sequence on mount
  useEffect(() => {
    let i = 0
    const interval = setInterval(() => {
      setFlashIdx(i)
      setTimeout(() => setFlashIdx(null), 350)
      i++
      if (i >= sequence.length) {
        clearInterval(interval)
        setTimeout(() => setShowing(false), 600)
      }
    }, 700)
    return () => clearInterval(interval)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  function handleTileTap(color: string) {
    if (locked) return
    const next = [...playerInput, color]
    setPlayerInput(next)
    if (next.length === sequence.length) {
      setLocked(true)
      sendIntent({ type: 'submit_puzzle_answer', answer_sequence: next })
      unlockTimer.current = setTimeout(() => setLocked(false), LOCK_TIMEOUT_MS)
    }
  }

  return (
    <div className="action-ui">
      <p className="action-ui__header">
        {showing ? 'Watch the sequence…' : 'Replay the sequence'}
      </p>
      <div className="action-ui__timer-bar-track">
        <div
          className={`action-ui__timer-bar${isWarning ? ' action-ui__timer-bar--warning' : ''}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="action-ui__puzzle-panel">
        <div className="action-ui__seq-tiles">
          {(['red', 'blue', 'green', 'yellow'] as const).map(color => {
            const isFlashing = showing && sequence[flashIdx ?? -1] === color
            return (
              <button
                key={color}
                className={`action-ui__seq-tile${isFlashing ? ' action-ui__seq-tile--flash' : ''}`}
                style={{ background: isFlashing ? TILE_COLORS[color] : `${TILE_COLORS[color]}33` }}
                disabled={showing || locked}
                onClick={() => handleTileTap(color)}
                aria-label={color}
              />
            )
          })}
        </div>
        {!showing && (
          <p className="action-ui__seq-progress">
            {playerInput.length} / {sequence.length}
          </p>
        )}
      </div>
    </div>
  )
}

// ── Resolved state ────────────────────────────────────────────────────────────

interface ResolvedProps {
  puzzle: PuzzleState
  latestHint?: HintPayload | null
  vibrate: (pattern: number | number[]) => void
}

function ResolvedPuzzle({ puzzle, latestHint, vibrate }: ResolvedProps) {
  const hasFired = useRef(false)

  useEffect(() => {
    if (puzzle.solved && !hasFired.current) {
      hasFired.current = true
      vibrate(100)
    }
  }, [puzzle.solved]) // eslint-disable-line react-hooks/exhaustive-deps

  if (puzzle.solved && puzzle.hint_pending && !latestHint) {
    return (
      <div className="action-ui action-ui--centered">
        <p className="action-ui__hint-pending">✓ Clue incoming…</p>
      </div>
    )
  }

  if (puzzle.solved && latestHint) {
    return (
      <div className="action-ui action-ui--centered">
        <div className="action-ui__hint-box">
          <p className="action-ui__hint-label">📜 Archive Clue</p>
          <p className="action-ui__hint">{latestHint.text}</p>
          {latestHint.expires_after_round !== null && (
            <p className="action-ui__hint-expiry">
              Expires after round {latestHint.expires_after_round}
            </p>
          )}
        </div>
        <p className="action-ui__rest">Rest…</p>
      </div>
    )
  }

  if (puzzle.solved === false) {
    return (
      <div className="action-ui action-ui--centered">
        <p className="action-ui__no-clue">No clue this round.</p>
        <p className="action-ui__rest">Rest…</p>
      </div>
    )
  }

  return (
    <div className="action-ui action-ui--centered">
      <p className="action-ui__rest">Rest…</p>
    </div>
  )
}
