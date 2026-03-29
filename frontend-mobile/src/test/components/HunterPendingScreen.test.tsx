import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import HunterPendingScreen from '../../components/HunterPendingScreen/HunterPendingScreen'
import { makeGameState, makePlayer } from '../fixtures'

vi.mock('../../hooks/useHaptics', () => ({
  useHaptics: () => ({ vibrate: vi.fn() }),
}))

describe('HunterPendingScreen', () => {
  const sendIntent = vi.fn()
  const myPlayer = makePlayer({ player_id: 'p1', display_name: 'Alice', is_alive: false })

  beforeEach(() => {
    sendIntent.mockReset()
  })

  it('renders alive players excluding self', () => {
    const gameState = makeGameState()
    render(<HunterPendingScreen gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />)
    expect(screen.getByText('Bob')).toBeInTheDocument()
    expect(screen.getByText('Carol')).toBeInTheDocument()
    expect(screen.queryByText('Alice')).not.toBeInTheDocument()
  })

  it('excludes dead players from target list', () => {
    const gameState = makeGameState({
      players: {
        p1: makePlayer({ player_id: 'p1', display_name: 'Alice', is_alive: false }),
        p2: makePlayer({ player_id: 'p2', display_name: 'Bob',   is_alive: true }),
        p3: makePlayer({ player_id: 'p3', display_name: 'Dead',  is_alive: false }),
      },
    })
    render(<HunterPendingScreen gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />)
    expect(screen.getByText('Bob')).toBeInTheDocument()
    expect(screen.queryByText('Dead')).not.toBeInTheDocument()
  })

  it('confirm button is disabled until a target is selected', () => {
    const gameState = makeGameState()
    render(<HunterPendingScreen gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />)
    expect(screen.getByRole('button', { name: 'Fire' })).toBeDisabled()
  })

  it('sends hunter_revenge intent with selected target_id on confirm', async () => {
    const user = userEvent.setup()
    const gameState = makeGameState()
    render(<HunterPendingScreen gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />)
    await user.click(screen.getByText('Bob'))
    await user.click(screen.getByRole('button', { name: 'Fire' }))
    expect(sendIntent).toHaveBeenCalledWith({ type: 'hunter_revenge', target_id: 'p2' })
  })
})
