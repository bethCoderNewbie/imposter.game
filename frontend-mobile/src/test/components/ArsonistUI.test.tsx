import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ArsonistUI from '../../components/NightActionShell/ArsonistUI'
import { makeGameState, makePlayer } from '../fixtures'

vi.mock('../../hooks/useHaptics', () => ({
  useHaptics: () => ({ vibrate: vi.fn() }),
}))

describe('ArsonistUI', () => {
  const sendIntent = vi.fn()
  const myPlayer = makePlayer({ player_id: 'p1', display_name: 'Alice', role: 'arsonist' })

  beforeEach(() => {
    sendIntent.mockReset()
  })

  it('defaults to douse mode with target picker visible', () => {
    const gameState = makeGameState()
    render(<ArsonistUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />)
    expect(screen.getByText('Choose who to douse')).toBeInTheDocument()
    expect(screen.getByText('Bob')).toBeInTheDocument()
  })

  it('douse confirm sends submit_night_action with arsonist_action douse and target_id', async () => {
    const user = userEvent.setup()
    const gameState = makeGameState()
    const { container } = render(
      <ArsonistUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />
    )
    await user.click(screen.getByText('Bob'))
    await user.click(container.querySelector('.action-ui__confirm')!)
    expect(sendIntent).toHaveBeenCalledWith({
      type: 'submit_night_action',
      arsonist_action: 'douse',
      target_id: 'p2',
    })
  })

  it('ignite button is disabled when doused_player_ids is empty', () => {
    const gameState = makeGameState()
    render(<ArsonistUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />)
    expect(screen.getByRole('button', { name: /Ignite/ })).toBeDisabled()
  })

  it('ignite button shows count and is enabled when players are doused', () => {
    const playerWithDoused = makePlayer({
      player_id: 'p1',
      display_name: 'Alice',
      role: 'arsonist',
      doused_player_ids: ['p2', 'p3'],
    })
    const gameState = makeGameState()
    render(<ArsonistUI gameState={gameState} myPlayer={playerWithDoused} sendIntent={sendIntent} />)
    expect(screen.getByRole('button', { name: 'Ignite (2)' })).not.toBeDisabled()
  })

  it('switching to ignite mode hides picker and shows ignite header', async () => {
    const user = userEvent.setup()
    const playerWithDoused = makePlayer({
      player_id: 'p1',
      display_name: 'Alice',
      role: 'arsonist',
      doused_player_ids: ['p2'],
    })
    const gameState = makeGameState()
    render(<ArsonistUI gameState={gameState} myPlayer={playerWithDoused} sendIntent={sendIntent} />)
    await user.click(screen.getByRole('button', { name: 'Ignite (1)' }))
    expect(screen.queryByText('Choose who to douse')).not.toBeInTheDocument()
    expect(screen.getByText(/Ignite 1 doused player/)).toBeInTheDocument()
  })

  it('ignite confirm sends submit_night_action with arsonist_action ignite', async () => {
    const user = userEvent.setup()
    const playerWithDoused = makePlayer({
      player_id: 'p1',
      display_name: 'Alice',
      role: 'arsonist',
      doused_player_ids: ['p2'],
    })
    const gameState = makeGameState()
    const { container } = render(
      <ArsonistUI gameState={gameState} myPlayer={playerWithDoused} sendIntent={sendIntent} />
    )
    await user.click(screen.getByRole('button', { name: 'Ignite (1)' }))
    await user.click(container.querySelector('.action-ui__confirm')!)
    expect(sendIntent).toHaveBeenCalledWith({
      type: 'submit_night_action',
      arsonist_action: 'ignite',
    })
  })
})
