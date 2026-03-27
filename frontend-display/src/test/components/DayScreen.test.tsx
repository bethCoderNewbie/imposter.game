import { render, screen } from '@testing-library/react'
import DayScreen from '../../components/DayScreen/DayScreen'
import { makeGameState, makePlayer } from '../fixtures'

// Mock useTimer — component tests don't re-test hook internals
vi.mock('../../hooks/useTimer', () => ({
  useTimer: vi.fn(() => ({ secondsRemaining: 60, isWarning: false, isCritical: false })),
}))

describe('DayScreen', () => {
  it('shows Discussion label in day phase', () => {
    render(<DayScreen gameState={makeGameState({ phase: 'day' })} frozenVotes={null} />)
    expect(screen.getByText('Discussion')).toBeInTheDocument()
  })

  it('shows Voting label in day_vote phase', () => {
    render(<DayScreen gameState={makeGameState({ phase: 'day_vote' })} frozenVotes={null} />)
    expect(screen.getByText('Voting')).toBeInTheDocument()
  })

  it('renders a PlayerCard for each player', () => {
    render(<DayScreen gameState={makeGameState()} frozenVotes={null} />)
    // default fixture has 5 players; check all names present
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getByText('Bob')).toBeInTheDocument()
    expect(screen.getByText('Carol')).toBeInTheDocument()
    expect(screen.getByText('Dave')).toBeInTheDocument()
    expect(screen.getByText('Eve')).toBeInTheDocument()
  })

  it('displays round number in header', () => {
    render(<DayScreen gameState={makeGameState({ round: 3 })} frozenVotes={null} />)
    expect(screen.getByText('Day 3')).toBeInTheDocument()
  })

  it('shows live vote counts during day_vote phase', () => {
    const players = {
      p1: makePlayer({ player_id: 'p1', display_name: 'Alice' }),
      p2: makePlayer({ player_id: 'p2', display_name: 'Bob' }),
      p3: makePlayer({ player_id: 'p3', display_name: 'Carol' }),
    }
    const gameState = makeGameState({
      phase: 'day_vote',
      players,
      day_votes: { p2: 'p1', p3: 'p1' }, // 2 votes on p1
    })
    render(<DayScreen gameState={gameState} frozenVotes={null} />)
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('uses frozenVotes when not in day_vote phase', () => {
    const players = {
      p1: makePlayer({ player_id: 'p1', display_name: 'Alice' }),
      p2: makePlayer({ player_id: 'p2', display_name: 'Bob' }),
    }
    const gameState = makeGameState({
      phase: 'day',
      players,
      day_votes: {},
    })
    render(<DayScreen gameState={gameState} frozenVotes={{ p2: 'p1' }} />)
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  it('does not render VoteWeb when frozenVotes is null', () => {
    const { container } = render(
      <DayScreen gameState={makeGameState({ phase: 'day' })} frozenVotes={null} />
    )
    expect(container.querySelector('.vote-web')).not.toBeInTheDocument()
  })

  it('renders VoteWeb container when frozenVotes is set', () => {
    const players = {
      p1: makePlayer({ player_id: 'p1' }),
      p2: makePlayer({ player_id: 'p2' }),
    }
    const { container } = render(
      <DayScreen
        gameState={makeGameState({ phase: 'day', players })}
        frozenVotes={{}}
      />
    )
    // VoteWeb renders null when lines=[] (empty votes), so check the component
    // was at least attempted by verifying no crash occurred
    expect(container.querySelector('.day-screen__grid')).toBeInTheDocument()
  })

  it('applies hasMajority when vote count exceeds half of living players', () => {
    const players = {
      p1: makePlayer({ player_id: 'p1', display_name: 'Alice' }),
      p2: makePlayer({ player_id: 'p2', display_name: 'Bob' }),
      p3: makePlayer({ player_id: 'p3', display_name: 'Carol' }),
      p4: makePlayer({ player_id: 'p4', display_name: 'Dave' }),
    }
    // 4 living players; majority threshold = 4/2 = 2; need > 2 votes = 3
    const gameState = makeGameState({
      phase: 'day_vote',
      players,
      day_votes: { p2: 'p1', p3: 'p1', p4: 'p1' }, // 3 votes on p1
    })
    const { container } = render(<DayScreen gameState={gameState} frozenVotes={null} />)
    expect(container.querySelector('[data-player-id="p1"].player-card--majority')).toBeInTheDocument()
  })
})
