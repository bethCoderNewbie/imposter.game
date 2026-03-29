import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import SerialKillerUI from '../../components/NightActionShell/SerialKillerUI'
import { makeGameState, makePlayer } from '../fixtures'

vi.mock('../../hooks/useHaptics', () => ({
  useHaptics: () => ({ vibrate: vi.fn() }),
}))

describe('SerialKillerUI', () => {
  const sendIntent = vi.fn()
  const myPlayer = makePlayer({ player_id: 'p1', display_name: 'Alice', role: 'serial_killer' })

  beforeEach(() => {
    sendIntent.mockReset()
  })

  it('shows alive players excluding self', () => {
    const gameState = makeGameState()
    render(<SerialKillerUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />)
    expect(screen.getByText('Bob')).toBeInTheDocument()
    expect(screen.queryByText('Alice')).not.toBeInTheDocument()
  })

  it('confirm button is disabled until target selected', () => {
    const gameState = makeGameState()
    render(<SerialKillerUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />)
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled()
  })

  it('sends submit_night_action with target_id on confirm', async () => {
    const user = userEvent.setup()
    const gameState = makeGameState()
    render(<SerialKillerUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />)
    await user.click(screen.getByText('Bob'))
    await user.click(screen.getByRole('button', { name: 'Confirm' }))
    expect(sendIntent).toHaveBeenCalledWith({ type: 'submit_night_action', target_id: 'p2' })
  })

  it('applies wolf CSS class to selected target row', async () => {
    const user = userEvent.setup()
    const gameState = makeGameState()
    const { container } = render(
      <SerialKillerUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />
    )
    await user.click(screen.getByText('Bob'))
    const selectedRow = container.querySelector('.action-ui__row--wolf')
    expect(selectedRow).toBeInTheDocument()
    expect(selectedRow).toHaveTextContent('Bob')
  })
})
