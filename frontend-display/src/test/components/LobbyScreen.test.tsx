import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import LobbyScreen from '../../components/LobbyScreen/LobbyScreen'
import { makeGameState, makePlayer } from '../fixtures'

afterEach(() => vi.unstubAllGlobals())

function makeFivePlayers() {
  return {
    p1: makePlayer({ player_id: 'p1', display_name: 'Alice' }),
    p2: makePlayer({ player_id: 'p2', display_name: 'Bob' }),
    p3: makePlayer({ player_id: 'p3', display_name: 'Carol' }),
    p4: makePlayer({ player_id: 'p4', display_name: 'Dave' }),
    p5: makePlayer({ player_id: 'p5', display_name: 'Eve' }),
  }
}

describe('LobbyScreen', () => {
  it('renders a QR code SVG element', () => {
    const { container } = render(
      <LobbyScreen gameState={makeGameState()} />
    )
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('renders the game_id as room code', () => {
    render(<LobbyScreen gameState={makeGameState({ game_id: 'ROOM99' })} />)
    expect(screen.getByText('ROOM99')).toBeInTheDocument()
  })

  it('shows joined count', () => {
    render(<LobbyScreen gameState={makeGameState()} />)
    // 5 players, player_count = 8 in config
    expect(screen.getByText(/5 \/ 8 joined/i)).toBeInTheDocument()
  })

  it('renders a PlayerAvatar for each player', () => {
    const { container } = render(<LobbyScreen gameState={makeGameState()} />)
    expect(container.querySelectorAll('.player-avatar')).toHaveLength(5)
  })

  it('disables Start button and shows needs-more text when fewer than 5 players', () => {
    const threePlayerState = makeGameState({
      players: {
        p1: makePlayer({ player_id: 'p1' }),
        p2: makePlayer({ player_id: 'p2' }),
        p3: makePlayer({ player_id: 'p3' }),
      },
    })
    render(<LobbyScreen gameState={threePlayerState} hostSecret="secret" gameId="G1" />)
    const btn = screen.getByRole('button')
    expect(btn).toBeDisabled()
    expect(btn).toHaveTextContent(/need 2 more players/i)
  })

  it('enables Start Game button at exactly 5 players', () => {
    render(
      <LobbyScreen
        gameState={makeGameState({ players: makeFivePlayers() })}
        hostSecret="secret"
        gameId="G1"
      />
    )
    const btn = screen.getByRole('button', { name: /start game/i })
    expect(btn).toBeEnabled()
  })

  it('shows Waiting for host text when no hostSecret is provided', () => {
    render(<LobbyScreen gameState={makeGameState({ players: makeFivePlayers() })} />)
    expect(screen.getByText(/waiting for host to start/i)).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('shows Dealing roles text during role_deal phase', () => {
    render(
      <LobbyScreen
        gameState={makeGameState({ phase: 'role_deal' })}
        hostSecret="s"
        gameId="G1"
      />
    )
    expect(screen.getByText(/dealing roles/i)).toBeInTheDocument()
  })

  it('calls POST /api/games/{id}/start on Start click', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({}) }))
    render(
      <LobbyScreen
        gameState={makeGameState({ players: makeFivePlayers(), game_id: 'GAMEX' })}
        hostSecret="my-secret"
        gameId="GAMEX"
      />
    )
    await userEvent.click(screen.getByRole('button', { name: /start game/i }))
    await waitFor(() =>
      expect(vi.mocked(fetch)).toHaveBeenCalledWith(
        '/api/games/GAMEX/start',
        expect.objectContaining({ method: 'POST' })
      )
    )
  })

  it('disables Start button while start request is in flight', async () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})))
    render(
      <LobbyScreen
        gameState={makeGameState({ players: makeFivePlayers() })}
        hostSecret="s"
        gameId="G1"
      />
    )
    await userEvent.click(screen.getByRole('button', { name: /start game/i }))
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('shows "Need 1 more player" (singular) when 4 players present', () => {
    const fourPlayers = {
      p1: makePlayer({ player_id: 'p1' }),
      p2: makePlayer({ player_id: 'p2' }),
      p3: makePlayer({ player_id: 'p3' }),
      p4: makePlayer({ player_id: 'p4' }),
    }
    render(
      <LobbyScreen
        gameState={makeGameState({ players: fourPlayers })}
        hostSecret="s"
        gameId="G1"
      />
    )
    expect(screen.getByRole('button')).toHaveTextContent('Need 1 more player')
  })
})
