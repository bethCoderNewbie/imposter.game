import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import GameOverScreen from '../../components/GameOverScreen/GameOverScreen'
import { makeGameState, makePlayer, makeElimination } from '../fixtures'

describe('GameOverScreen', () => {
  const onPlayAgain = vi.fn()

  beforeEach(() => {
    onPlayAgain.mockReset()
  })

  it('shows "Village Wins!" when winner is village', () => {
    const gameState = makeGameState({ winner: 'village' })
    render(<GameOverScreen gameState={gameState} myPlayerId="p1" onPlayAgain={onPlayAgain} />)
    expect(screen.getByRole('heading', { name: 'Village Wins!' })).toBeInTheDocument()
  })

  it('shows "Wolves Win!" when winner is werewolf', () => {
    const gameState = makeGameState({ winner: 'werewolf' })
    render(<GameOverScreen gameState={gameState} myPlayerId="p1" onPlayAgain={onPlayAgain} />)
    expect(screen.getByRole('heading', { name: 'Wolves Win!' })).toBeInTheDocument()
  })

  it('shows "<name> Wins!" when winner is neutral with known winner_player_id', () => {
    const gameState = makeGameState({
      winner: 'neutral',
      winner_player_id: 'p1',
      players: {
        p1: makePlayer({ player_id: 'p1', display_name: 'Jester', is_alive: false }),
      },
    })
    render(<GameOverScreen gameState={gameState} myPlayerId="p1" onPlayAgain={onPlayAgain} />)
    expect(screen.getByRole('heading', { name: 'Jester Wins!' })).toBeInTheDocument()
  })

  it('shows "Neutral Wins!" when winner_player_id not found in players', () => {
    const gameState = makeGameState({
      winner: 'neutral',
      winner_player_id: 'unknown-id',
    })
    render(<GameOverScreen gameState={gameState} myPlayerId="p1" onPlayAgain={onPlayAgain} />)
    expect(screen.getByRole('heading', { name: 'Neutral Wins!' })).toBeInTheDocument()
  })

  it('renders all players in the grid (alive and dead)', () => {
    const gameState = makeGameState({
      players: {
        p1: makePlayer({ player_id: 'p1', display_name: 'Alice', is_alive: true }),
        p2: makePlayer({ player_id: 'p2', display_name: 'Bob',   is_alive: false }),
      },
      winner: 'village',
    })
    render(<GameOverScreen gameState={gameState} myPlayerId="p1" onPlayAgain={onPlayAgain} />)
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getByText('Bob')).toBeInTheDocument()
  })

  it('renders elimination log entries', () => {
    const gameState = makeGameState({
      winner: 'village',
      elimination_log: [
        makeElimination({ round: 1, player_id: 'p2', cause: 'wolf_kill' }),
      ],
    })
    render(<GameOverScreen gameState={gameState} myPlayerId="p1" onPlayAgain={onPlayAgain} />)
    expect(screen.getByText('R1')).toBeInTheDocument()
    expect(screen.getByText('Killed by wolves')).toBeInTheDocument()
  })

  it('"Play Again" button triggers onPlayAgain callback', async () => {
    const user = userEvent.setup()
    const gameState = makeGameState({ winner: 'village' })
    render(<GameOverScreen gameState={gameState} myPlayerId="p1" onPlayAgain={onPlayAgain} />)
    await user.click(screen.getByRole('button', { name: 'Play Again' }))
    expect(onPlayAgain).toHaveBeenCalledOnce()
  })
})
