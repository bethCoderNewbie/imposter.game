import { render, screen } from '@testing-library/react'
import NightResolution from '../../components/NightResolution/NightResolution'
import { makeGameState, makeElimination } from '../fixtures'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('NightResolution', () => {
  it('shows dawn message when there are no night deaths', () => {
    render(
      <NightResolution
        gameState={makeGameState({ elimination_log: [], round: 1 })}
        onComplete={vi.fn()}
      />
    )
    expect(screen.getByText(/dawn breaks/i)).toBeInTheDocument()
  })

  it('shows body-discovered message when a night death occurred this round', () => {
    const gameState = makeGameState({
      round: 2,
      elimination_log: [makeElimination({ phase: 'night', round: 2, player_id: 'p2' })],
    })
    render(<NightResolution gameState={gameState} onComplete={vi.fn()} />)
    expect(screen.getByText(/a body is discovered/i)).toBeInTheDocument()
  })

  it('renders dead player name for each night death this round', () => {
    const gameState = makeGameState({
      round: 1,
      elimination_log: [makeElimination({ phase: 'night', round: 1, player_id: 'p2' })],
    })
    render(<NightResolution gameState={gameState} onComplete={vi.fn()} />)
    expect(screen.getByText('Bob')).toBeInTheDocument()
  })

  it('does not render elimination from a previous round', () => {
    const gameState = makeGameState({
      round: 2,
      elimination_log: [makeElimination({ phase: 'night', round: 1, player_id: 'p2' })],
    })
    render(<NightResolution gameState={gameState} onComplete={vi.fn()} />)
    // round 1 death should not appear when current round is 2
    expect(screen.queryByText('Bob')).not.toBeInTheDocument()
    expect(screen.getByText(/dawn breaks/i)).toBeInTheDocument()
  })

  it('calls onComplete after 4000ms', () => {
    const onComplete = vi.fn()
    render(
      <NightResolution gameState={makeGameState()} onComplete={onComplete} />
    )
    expect(onComplete).not.toHaveBeenCalled()
    vi.advanceTimersByTime(4000)
    expect(onComplete).toHaveBeenCalledTimes(1)
  })

  it('does not call onComplete before 4000ms', () => {
    const onComplete = vi.fn()
    render(
      <NightResolution gameState={makeGameState()} onComplete={onComplete} />
    )
    vi.advanceTimersByTime(3999)
    expect(onComplete).not.toHaveBeenCalled()
  })

  it('clears timeout on unmount so onComplete is not called after unmount', () => {
    const onComplete = vi.fn()
    const { unmount } = render(
      <NightResolution gameState={makeGameState()} onComplete={onComplete} />
    )
    unmount()
    vi.advanceTimersByTime(4000)
    expect(onComplete).not.toHaveBeenCalled()
  })
})
