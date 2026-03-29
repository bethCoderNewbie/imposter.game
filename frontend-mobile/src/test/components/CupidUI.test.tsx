import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CupidUI from '../../components/NightActionShell/CupidUI'
import { makeGameState, makePlayer } from '../fixtures'

vi.mock('../../hooks/useHaptics', () => ({
  useHaptics: () => ({ vibrate: vi.fn() }),
}))

describe('CupidUI', () => {
  const sendIntent = vi.fn()
  const myPlayer = makePlayer({ player_id: 'p1', display_name: 'Alice', role: 'cupid' })

  beforeEach(() => {
    sendIntent.mockReset()
  })

  it('starts in step 1: shows "Choose the first lover" header', () => {
    const gameState = makeGameState()
    render(<CupidUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />)
    expect(screen.getByText('Choose the first lover')).toBeInTheDocument()
  })

  it('selecting first lover advances to step 2 with updated header', async () => {
    const user = userEvent.setup()
    const gameState = makeGameState()
    render(<CupidUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />)
    await user.click(screen.getByText('Bob'))
    expect(screen.getByText('Choose the second lover')).toBeInTheDocument()
  })

  it('targetA is disabled/excluded in step 2 picker', async () => {
    const user = userEvent.setup()
    const gameState = makeGameState()
    render(<CupidUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />)
    await user.click(screen.getByText('Bob'))
    // Bob's button should be disabled in step 2
    const bobButton = screen.getByRole('button', { name: /Bob/ })
    expect(bobButton).toBeDisabled()
  })

  it('confirm "Link them" button hidden until both lovers selected', async () => {
    const user = userEvent.setup()
    const gameState = makeGameState()
    render(<CupidUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />)
    expect(screen.queryByRole('button', { name: 'Link them' })).not.toBeInTheDocument()
    await user.click(screen.getByText('Bob'))
    expect(screen.queryByRole('button', { name: 'Link them' })).not.toBeInTheDocument()
    await user.click(screen.getByText('Carol'))
    expect(screen.getByRole('button', { name: 'Link them' })).toBeInTheDocument()
  })

  it('sends submit_night_action with link_target_a and link_target_b', async () => {
    const user = userEvent.setup()
    const gameState = makeGameState()
    render(<CupidUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />)
    await user.click(screen.getByText('Bob'))
    await user.click(screen.getByText('Carol'))
    await user.click(screen.getByRole('button', { name: 'Link them' }))
    expect(sendIntent).toHaveBeenCalledWith({
      type: 'submit_night_action',
      link_target_a: 'p2',
      link_target_b: 'p3',
    })
  })
})
