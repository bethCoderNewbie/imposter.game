import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import DayDiscussionScreen from '../../components/DayDiscussionScreen/DayDiscussionScreen'
import { makeGameState, makePlayer } from '../fixtures'
import { useTimer } from '../../hooks/useTimer'

vi.mock('../../hooks/useTimer', () => ({
  useTimer: vi.fn(() => ({ secondsRemaining: 120, isWarning: false, isCritical: false })),
}))

const mockUseTimer = vi.mocked(useTimer)

describe('DayDiscussionScreen', () => {
  beforeEach(() => {
    mockUseTimer.mockReturnValue({ secondsRemaining: 120, isWarning: false, isCritical: false })
    localStorage.clear()
  })

  // ── Timer display ─────────────────────────────────────────────────────────

  it('renders timer in MM:SS format', () => {
    mockUseTimer.mockReturnValue({ secondsRemaining: 125, isWarning: false, isCritical: false })
    const gameState = makeGameState({ phase: 'day' })
    render(<DayDiscussionScreen gameState={gameState} myPlayerId="p1" />)
    expect(screen.getByText('02:05')).toBeInTheDocument()
  })

  it('applies timer--warning class when isWarning', () => {
    mockUseTimer.mockReturnValue({ secondsRemaining: 25, isWarning: true, isCritical: false })
    const gameState = makeGameState({ phase: 'day' })
    const { container } = render(<DayDiscussionScreen gameState={gameState} myPlayerId="p1" />)
    expect(container.querySelector('.day-discussion__timer')).toHaveClass('timer--warning')
  })

  it('applies timer--critical (not timer--warning) when isCritical', () => {
    mockUseTimer.mockReturnValue({ secondsRemaining: 5, isWarning: true, isCritical: true })
    const gameState = makeGameState({ phase: 'day' })
    const { container } = render(<DayDiscussionScreen gameState={gameState} myPlayerId="p1" />)
    const timer = container.querySelector('.day-discussion__timer')
    expect(timer).toHaveClass('timer--critical')
    expect(timer).not.toHaveClass('timer--warning')
  })

  // ── Notepad ────────────────────────────────────────────────────────────────

  it('notepad is hidden by default', () => {
    const gameState = makeGameState({ phase: 'day' })
    render(<DayDiscussionScreen gameState={gameState} myPlayerId="p1" />)
    expect(screen.queryByText('Bob')).not.toBeInTheDocument()
  })

  it('notepad toggles open on button click', async () => {
    const user = userEvent.setup()
    const gameState = makeGameState({ phase: 'day' })
    render(<DayDiscussionScreen gameState={gameState} myPlayerId="p1" />)
    await user.click(screen.getByText(/Notes/))
    expect(screen.getByText('Bob')).toBeInTheDocument()
  })

  it('notepad shows only alive non-self players', async () => {
    const user = userEvent.setup()
    const gameState = makeGameState({
      phase: 'day',
      players: {
        p1: makePlayer({ player_id: 'p1', display_name: 'Alice', is_alive: true }),
        p2: makePlayer({ player_id: 'p2', display_name: 'Bob',   is_alive: true }),
        p3: makePlayer({ player_id: 'p3', display_name: 'Dead',  is_alive: false }),
      },
    })
    render(<DayDiscussionScreen gameState={gameState} myPlayerId="p1" />)
    await user.click(screen.getByText(/Notes/))
    expect(screen.getByText('Bob')).toBeInTheDocument()
    expect(screen.queryByText('Alice')).not.toBeInTheDocument()
    expect(screen.queryByText('Dead')).not.toBeInTheDocument()
  })

  // ── Tag cycling ────────────────────────────────────────────────────────────

  it('tag cycles ? → Sus → Safe → ?', async () => {
    const user = userEvent.setup()
    const gameState = makeGameState({
      phase: 'day',
      players: {
        p1: makePlayer({ player_id: 'p1', display_name: 'Alice', is_alive: true }),
        p2: makePlayer({ player_id: 'p2', display_name: 'Bob',   is_alive: true }),
      },
    })
    render(<DayDiscussionScreen gameState={gameState} myPlayerId="p1" />)
    await user.click(screen.getByText(/Notes/))

    const tag = screen.getByRole('button', { name: '?' })
    await user.click(tag)
    expect(screen.getByRole('button', { name: 'Sus' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Sus' }))
    expect(screen.getByRole('button', { name: 'Safe' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Safe' }))
    expect(screen.getByRole('button', { name: '?' })).toBeInTheDocument()
  })

  it('Sus/Safe tags persisted to localStorage; ? removes key', async () => {
    const user = userEvent.setup()
    const gameState = makeGameState({
      phase: 'day',
      players: {
        p1: makePlayer({ player_id: 'p1', display_name: 'Alice', is_alive: true }),
        p2: makePlayer({ player_id: 'p2', display_name: 'Bob',   is_alive: true }),
      },
    })
    render(<DayDiscussionScreen gameState={gameState} myPlayerId="p1" />)
    await user.click(screen.getByText(/Notes/))

    await user.click(screen.getByRole('button', { name: '?' }))   // → Sus
    expect(localStorage.getItem('ww_note_test-game-001_p1_p2')).toBe('Sus')

    await user.click(screen.getByRole('button', { name: 'Sus' })) // → Safe
    expect(localStorage.getItem('ww_note_test-game-001_p1_p2')).toBe('Safe')

    await user.click(screen.getByRole('button', { name: 'Safe' })) // → ?
    expect(localStorage.getItem('ww_note_test-game-001_p1_p2')).toBeNull()
  })

  it('pruneStaleNotes removes keys from other games on mount', () => {
    localStorage.setItem('ww_note_old-game-999_p1_p2', 'Sus')
    localStorage.setItem('ww_note_test-game-001_p1_p2', 'Safe')
    const gameState = makeGameState({ phase: 'day' })
    render(<DayDiscussionScreen gameState={gameState} myPlayerId="p1" />)
    expect(localStorage.getItem('ww_note_old-game-999_p1_p2')).toBeNull()
    expect(localStorage.getItem('ww_note_test-game-001_p1_p2')).toBe('Safe')
  })

  // ── Seer panel ─────────────────────────────────────────────────────────────

  it('seer panel not rendered for non-seer player', () => {
    const gameState = makeGameState({
      phase: 'day',
      players: {
        p1: makePlayer({ player_id: 'p1', role: 'villager' }),
        p2: makePlayer({ player_id: 'p2' }),
      },
      seer_knowledge: { p2: 'wolf' },
    })
    render(<DayDiscussionScreen gameState={gameState} myPlayerId="p1" />)
    expect(screen.queryByText(/Your Intel/)).not.toBeInTheDocument()
  })

  it('seer panel rendered for seer when seer_knowledge has entries', () => {
    const gameState = makeGameState({
      phase: 'day',
      players: {
        p1: makePlayer({ player_id: 'p1', role: 'seer' }),
        p2: makePlayer({ player_id: 'p2', display_name: 'Bob' }),
      },
      seer_knowledge: { p2: 'wolf' },
    })
    render(<DayDiscussionScreen gameState={gameState} myPlayerId="p1" />)
    expect(screen.getByText('🔮 Your Intel')).toBeInTheDocument()
    expect(screen.getByText(/WOLF/)).toBeInTheDocument()
  })
})
