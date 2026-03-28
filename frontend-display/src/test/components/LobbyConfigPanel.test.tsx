import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import LobbyConfigPanel from '../../components/LobbyConfigPanel/LobbyConfigPanel'
import { makeGameState } from '../fixtures'

function makeConfig(overrides = {}) {
  return { ...makeGameState().config, ...overrides }
}

describe('LobbyConfigPanel', () => {
  it('shows read-only row when no hostSecret', () => {
    render(<LobbyConfigPanel config={makeConfig()} />)
    expect(screen.getByText('Balanced')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('shows difficulty button group for host', () => {
    render(<LobbyConfigPanel config={makeConfig()} hostSecret="s" gameId="G1" />)
    expect(screen.getByRole('button', { name: 'Easy' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Balanced' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Hard' })).toBeInTheDocument()
  })

  it('active difficulty button reflects current config', () => {
    render(<LobbyConfigPanel config={makeConfig({ difficulty_level: 'hard' })} hostSecret="s" gameId="G1" />)
    expect(screen.getByRole('button', { name: 'Hard' })).toHaveClass('lobby-config-panel__difficulty-btn--active')
  })

  it('calls PATCH with difficulty_level on difficulty button click', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }))
    render(<LobbyConfigPanel config={makeConfig()} hostSecret="my-secret" gameId="GAMEX" />)
    await userEvent.click(screen.getByRole('button', { name: 'Hard' }))
    await waitFor(() =>
      expect(vi.mocked(fetch)).toHaveBeenCalledWith('/api/games/GAMEX/config',
        expect.objectContaining({
          method: 'PATCH',
          body: expect.stringContaining('"difficulty_level":"hard"'),
        })
      )
    )
    vi.unstubAllGlobals()
  })

  it('shows stepper buttons for each timer', () => {
    render(<LobbyConfigPanel config={makeConfig()} hostSecret="s" gameId="G1" />)
    expect(screen.getByText('Night')).toBeInTheDocument()
    expect(screen.getByText('Day')).toBeInTheDocument()
    expect(screen.getByText('Vote')).toBeInTheDocument()
  })

  it('calls PATCH with incremented timer on + click', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }))
    render(<LobbyConfigPanel config={makeConfig({ night_timer_seconds: 60 })} hostSecret="s" gameId="G1" />)
    const plusButtons = screen.getAllByText('+')
    await userEvent.click(plusButtons[0])  // first + is Night timer
    await waitFor(() =>
      expect(vi.mocked(fetch)).toHaveBeenCalledWith('/api/games/G1/config',
        expect.objectContaining({ body: expect.stringContaining('"night_timer_seconds":75') })
      )
    )
    vi.unstubAllGlobals()
  })

  it('disables all controls during in-flight PATCH', async () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})))
    render(<LobbyConfigPanel config={makeConfig()} hostSecret="s" gameId="G1" />)
    await userEvent.click(screen.getByRole('button', { name: 'Hard' }))
    screen.getAllByRole('button').forEach(btn => expect(btn).toBeDisabled())
    vi.unstubAllGlobals()
  })

  it('disables − button when timer is at minimum', () => {
    render(<LobbyConfigPanel config={makeConfig({ night_timer_seconds: 30 })} hostSecret="s" gameId="G1" />)
    const minusButtons = screen.getAllByText('−')
    expect(minusButtons[0]).toBeDisabled()  // Night at min
  })

  it('disables + button when timer is at maximum', () => {
    render(<LobbyConfigPanel config={makeConfig({ night_timer_seconds: 120 })} hostSecret="s" gameId="G1" />)
    const plusButtons = screen.getAllByText('+')
    expect(plusButtons[0]).toBeDisabled()  // Night at max
  })

  it('shows formatted timer values (seconds < 60 shows Xs)', () => {
    render(<LobbyConfigPanel config={makeConfig({ night_timer_seconds: 30 })} hostSecret="s" gameId="G1" />)
    expect(screen.getByText('30s')).toBeInTheDocument()
  })

  it('shows formatted timer values (seconds >= 60 shows M:SS)', () => {
    render(<LobbyConfigPanel config={makeConfig({ night_timer_seconds: 75 })} hostSecret="s" gameId="G1" />)
    expect(screen.getByText('1:15')).toBeInTheDocument()
  })
})
