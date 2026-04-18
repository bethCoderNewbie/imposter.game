import { useEffect, useRef, useState } from 'react'
import type { HintPayload, PuzzleState } from '../../types/game'
import './ActionUI.css'

const LOCK_TIMEOUT_MS = 4000

export interface PuzzleRendererProps {
  puzzle: PuzzleState
  sendIntent: (payload: Record<string, unknown>) => void
  latestHint?: HintPayload | null
  /** 'archive' uses submit_puzzle_answer intent; 'grid' uses submit_grid_answer intent */
  source: 'archive' | 'grid'
}

/** Renders an active or resolved PuzzleState. Used by both VillagerDecoyUI (Archive)
 *  and GridMapUI (grid nodes). correct_index is always stripped server-side. */
export default function PuzzleRenderer({ puzzle, sendIntent, latestHint, source }: PuzzleRendererProps) {
  if (puzzle.active) {
    return <ActivePuzzle puzzle={puzzle} sendIntent={sendIntent} source={source} />
  }
  return (
    <ResolvedPuzzle
      puzzle={puzzle}
      latestHint={latestHint}
      hintLabel={source === 'archive' ? '📜 Archive Clue' : '🔷 Grid Intel'}
    />
  )
}

// ── Active puzzle ─────────────────────────────────────────────────────────────

interface ActiveProps {
  puzzle: PuzzleState
  sendIntent: (payload: Record<string, unknown>) => void
  source: 'archive' | 'grid'
}

function ActivePuzzle({ puzzle, sendIntent, source }: ActiveProps) {
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
    return <SequencePuzzle puzzle={puzzle} sendIntent={sendIntent} pct={pct} isWarning={isWarning} source={source} />
  }

  if (puzzle.puzzle_type === 'hard_logic') {
    return <HardLogicPuzzle puzzle={puzzle} sendIntent={sendIntent} pct={pct} isWarning={isWarning} source={source} />
  }

  return <ChoicePuzzle puzzle={puzzle} sendIntent={sendIntent} pct={pct} isWarning={isWarning} source={source} />
}

// ── Multiple-choice puzzle (logic + math) ─────────────────────────────────────

interface ChoiceProps {
  puzzle: PuzzleState
  sendIntent: (payload: Record<string, unknown>) => void
  pct: number
  isWarning: boolean
  source: 'archive' | 'grid'
}

function ChoicePuzzle({ puzzle, sendIntent, pct, isWarning, source }: ChoiceProps) {
  const data = puzzle.puzzle_data as { question?: string; expression?: string; answer_options: string[] }
  const prompt = data.question ?? data.expression ?? ''
  const options = data.answer_options ?? []
  const [locked, setLocked] = useState(false)
  const unlockTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  function handleAnswer(i: number) {
    if (locked) return
    setLocked(true)
    const intentType = source === 'archive' ? 'submit_puzzle_answer' : 'submit_grid_answer'
    sendIntent({ type: intentType, answer_index: i })
    unlockTimer.current = setTimeout(() => setLocked(false), LOCK_TIMEOUT_MS)
  }

  useEffect(() => () => {
    if (unlockTimer.current) clearTimeout(unlockTimer.current)
  }, [])

  const headerText = source === 'archive'
    ? 'The Archives await. Solve the puzzle to earn a clue.'
    : 'Solve the node to extract intelligence.'

  return (
    <div className="action-ui">
      <p className="action-ui__header">{headerText}</p>
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

// ── Hard logic puzzle (two sequential questions, both required) ───────────────

function HardLogicPuzzle({ puzzle, sendIntent, pct, isWarning, source }: ChoiceProps) {
  const data = puzzle.puzzle_data as {
    q1: { question: string; answer_options: string[] }
    q2: { question: string; answer_options: string[] }
  }
  const [step, setStep] = useState<1 | 2>(1)
  const [q1Answer, setQ1Answer] = useState<number | null>(null)
  const [locked, setLocked] = useState(false)
  const unlockTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => () => {
    if (unlockTimer.current) clearTimeout(unlockTimer.current)
  }, [])

  function handleQ1(i: number) {
    if (locked) return
    setQ1Answer(i)
    setStep(2)
  }

  function handleQ2(i: number) {
    if (locked || q1Answer === null) return
    setLocked(true)
    const intentType = source === 'archive' ? 'submit_puzzle_answer' : 'submit_grid_answer'
    sendIntent({ type: intentType, answer_indices: [q1Answer, i] })
    unlockTimer.current = setTimeout(() => setLocked(false), LOCK_TIMEOUT_MS)
  }

  const currentQ = step === 1 ? data.q1 : data.q2
  const handleAnswer = step === 1 ? handleQ1 : handleQ2

  return (
    <div className="action-ui">
      <p className="action-ui__header">
        {step === 1 ? 'Question 1 of 2 — both must be correct.' : 'Question 2 of 2 — finish strong.'}
      </p>
      <div className="action-ui__timer-bar-track">
        <div
          className={`action-ui__timer-bar${isWarning ? ' action-ui__timer-bar--warning' : ''}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="action-ui__puzzle-panel">
        <p className="action-ui__puzzle-question">{currentQ.question}</p>
        <div className="action-ui__answer-grid">
          {currentQ.answer_options.map((opt, i) => (
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
  source: 'archive' | 'grid'
}

function SequencePuzzle({ puzzle, sendIntent, pct, isWarning, source }: SequenceProps) {
  const data = puzzle.puzzle_data as { sequence: string[] }
  const sequence = data.sequence ?? []
  const [flashIdx, setFlashIdx] = useState<number | null>(null)
  const [showing, setShowing] = useState(true)
  const [playerInput, setPlayerInput] = useState<string[]>([])
  const [locked, setLocked] = useState(false)
  const unlockTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => () => {
    if (unlockTimer.current) clearTimeout(unlockTimer.current)
  }, [])

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
      const intentType = source === 'archive' ? 'submit_puzzle_answer' : 'submit_grid_answer'
      sendIntent({ type: intentType, answer_sequence: next })
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
  hintLabel: string
}

function ResolvedPuzzle({ puzzle, latestHint, hintLabel }: ResolvedProps) {
  if (puzzle.solved && !latestHint) {
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
          <p className="action-ui__hint-label">{hintLabel}</p>
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
