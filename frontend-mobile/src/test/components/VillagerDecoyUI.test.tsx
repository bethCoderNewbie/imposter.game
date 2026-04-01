import { render, screen, act, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import VillagerDecoyUI from '../../components/NightActionShell/VillagerDecoyUI'
import { makePlayer } from '../fixtures'
import type { HintPayload, PuzzleState } from '../../types/game'

vi.mock('../../hooks/useHaptics', () => ({
  useHaptics: () => ({ vibrate: vi.fn() }),
}))

// Prevent rAF timer loop in tests — ActivePuzzle uses rAF for its progress bar
vi.spyOn(window, 'requestAnimationFrame').mockImplementation(() => 0)
vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => undefined)

const sendIntent = vi.fn()

function makeActivePuzzle(overrides: Partial<PuzzleState> = {}): PuzzleState {
  return {
    active: true,
    puzzle_type: 'logic',
    puzzle_data: {
      question: 'Which is not a mammal?',
      answer_options: ['Dog', 'Eagle', 'Cat', 'Whale'],
    },
    time_limit_seconds: 30,
    solved: null,
    ...overrides,
  }
}

describe('VillagerDecoyUI', () => {
  beforeEach(() => {
    sendIntent.mockReset()
  })

  // ── Null puzzle state ──────────────────────────────────────────────────────

  it('shows "Archives await" when puzzle_state is null', () => {
    const player = makePlayer({ puzzle_state: null })
    render(<VillagerDecoyUI myPlayer={player} sendIntent={sendIntent} />)
    expect(screen.getByText('The Archives await…')).toBeInTheDocument()
  })

  it('shows "Archives await" when puzzle_state is undefined', () => {
    const player = makePlayer()
    render(<VillagerDecoyUI myPlayer={player} sendIntent={sendIntent} />)
    expect(screen.getByText('The Archives await…')).toBeInTheDocument()
  })

  // ── Choice puzzle ──────────────────────────────────────────────────────────

  it('renders ChoicePuzzle for logic puzzle type', () => {
    const player = makePlayer({ puzzle_state: makeActivePuzzle({ puzzle_type: 'logic' }) })
    render(<VillagerDecoyUI myPlayer={player} sendIntent={sendIntent} />)
    expect(screen.getByText('Which is not a mammal?')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Eagle' })).toBeInTheDocument()
  })

  it('renders ChoicePuzzle for math puzzle type using expression field', () => {
    const player = makePlayer({
      puzzle_state: makeActivePuzzle({
        puzzle_type: 'math',
        puzzle_data: { expression: '2 + 2', answer_options: ['3', '4', '5', '6'] },
      }),
    })
    render(<VillagerDecoyUI myPlayer={player} sendIntent={sendIntent} />)
    expect(screen.getByText('2 + 2')).toBeInTheDocument()
  })

  it('clicking answer calls sendIntent with answer_index and disables buttons', async () => {
    const user = userEvent.setup()
    const player = makePlayer({
      puzzle_state: makeActivePuzzle({
        puzzle_data: {
          question: 'Pick one',
          answer_options: ['A', 'B', 'C', 'D'],
        },
      }),
    })
    render(<VillagerDecoyUI myPlayer={player} sendIntent={sendIntent} />)
    await user.click(screen.getByRole('button', { name: 'B' }))
    expect(sendIntent).toHaveBeenCalledWith({ type: 'submit_puzzle_answer', answer_index: 1 })
    expect(screen.getByRole('button', { name: 'A' })).toBeDisabled()
  })

  it('buttons re-enable after LOCK_TIMEOUT_MS with no state update', () => {
    vi.useFakeTimers()
    const player = makePlayer({
      puzzle_state: makeActivePuzzle({
        puzzle_data: { question: 'Pick', answer_options: ['X', 'Y'] },
      }),
    })
    render(<VillagerDecoyUI myPlayer={player} sendIntent={sendIntent} />)
    fireEvent.click(screen.getByRole('button', { name: 'X' }))
    expect(screen.getByRole('button', { name: 'Y' })).toBeDisabled()
    act(() => { vi.advanceTimersByTime(4000) })
    expect(screen.getByRole('button', { name: 'Y' })).not.toBeDisabled()
    vi.useRealTimers()
  })

  // ── Sequence puzzle ────────────────────────────────────────────────────────

  it('renders SequencePuzzle for sequence puzzle type', () => {
    const player = makePlayer({
      puzzle_state: makeActivePuzzle({
        puzzle_type: 'sequence',
        puzzle_data: { sequence: ['red', 'blue', 'green'] },
      }),
    })
    render(<VillagerDecoyUI myPlayer={player} sendIntent={sendIntent} />)
    expect(screen.getByText('Watch the sequence…')).toBeInTheDocument()
  })

  // ── Resolved puzzle states ─────────────────────────────────────────────────

  it('shows "Clue incoming" when solved and hint_pending but no latestHint', () => {
    const player = makePlayer({
      puzzle_state: {
        active: false,
        puzzle_type: 'logic',
        puzzle_data: {},
        time_limit_seconds: 30,
        solved: true,
        hint_pending: true,
      },
    })
    render(<VillagerDecoyUI myPlayer={player} sendIntent={sendIntent} />)
    expect(screen.getByText('✓ Clue incoming…')).toBeInTheDocument()
  })

  it('shows hint text when solved and latestHint provided', () => {
    const player = makePlayer({
      puzzle_state: {
        active: false,
        puzzle_type: 'logic',
        puzzle_data: {},
        time_limit_seconds: 30,
        solved: true,
        hint_pending: false,
      },
    })
    const hint: HintPayload = {
      type: 'hint_reward',
      hint_id: 'h1',
      category: 'wolf_count',
      text: 'There are 2 wolves.',
      round: 1,
      expires_after_round: 3,
    }
    render(<VillagerDecoyUI myPlayer={player} sendIntent={sendIntent} latestHint={hint} />)
    expect(screen.getByText('There are 2 wolves.')).toBeInTheDocument()
    expect(screen.getByText('Expires after round 3')).toBeInTheDocument()
  })

  it('shows "No clue this round" when solved is false', () => {
    const player = makePlayer({
      puzzle_state: {
        active: false,
        puzzle_type: 'logic',
        puzzle_data: {},
        time_limit_seconds: 30,
        solved: false,
      },
    })
    render(<VillagerDecoyUI myPlayer={player} sendIntent={sendIntent} />)
    expect(screen.getByText('No clue this round.')).toBeInTheDocument()
  })
})
