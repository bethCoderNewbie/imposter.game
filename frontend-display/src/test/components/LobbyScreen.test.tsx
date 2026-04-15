import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import LobbyScreen from '../../components/LobbyScreen/LobbyScreen'
import { useGameStore } from '../../store/gameStore'
import { makeGameState, makePlayer } from '../fixtures'

afterEach(() => vi.unstubAllGlobals())

beforeEach(() => {
  // Seed store with default 5 players before each test
  useGameStore.setState({ roster: Object.values(makeGameState().players) })
})

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
    // 5 connected players in store → "5 active / 5 joined"
    expect(screen.getByText(/5 active \/ 5 joined/i)).toBeInTheDocument()
  })

  it('renders a PlayerAvatar for each player in the parade', () => {
    const { container } = render(<LobbyScreen gameState={makeGameState()} />)
    // Parade shows connected players only; roster panel shows all (doubles count).
    // Scope to the parade container.
    const parade = container.querySelector('.lobby-screen__avatars')!
    expect(parade.querySelectorAll('.player-avatar')).toHaveLength(5)
  })

  it('disables Start button and shows needs-more text when fewer than 5 players', () => {
    useGameStore.setState({
      roster: [
        makePlayer({ player_id: 'p1' }),
        makePlayer({ player_id: 'p2' }),
        makePlayer({ player_id: 'p3' }),
      ],
    })
    const threePlayerState = makeGameState({
      players: {
        p1: makePlayer({ player_id: 'p1' }),
        p2: makePlayer({ player_id: 'p2' }),
        p3: makePlayer({ player_id: 'p3' }),
      },
    })
    render(<LobbyScreen gameState={threePlayerState} hostSecret="secret" gameId="G1" />)
    const btn = screen.getByRole('button', { name: /need 2 more players/i })
    expect(btn).toBeDisabled()
  })

  it('enables Start Game button at exactly 5 players', () => {
    useGameStore.setState({ roster: Object.values(makeFivePlayers()) })
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
    useGameStore.setState({ roster: Object.values(makeFivePlayers()) })
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
    useGameStore.setState({ roster: Object.values(makeFivePlayers()) })
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
    useGameStore.setState({ roster: Object.values(makeFivePlayers()) })
    render(
      <LobbyScreen
        gameState={makeGameState({ players: makeFivePlayers() })}
        hostSecret="s"
        gameId="G1"
      />
    )
    await userEvent.click(screen.getByRole('button', { name: /start game/i }))
    expect(screen.getByRole('button', { name: /starting/i })).toBeDisabled()
  })

  it('renders LobbyConfigPanel with config', () => {
    render(<LobbyScreen gameState={makeGameState()} />)
    // Spectator view shows read-only difficulty badge
    expect(screen.getByText('Balanced')).toBeInTheDocument()
  })

  it('shows "Need 1 more player" (singular) when 4 players present', () => {
    const fourPlayers = {
      p1: makePlayer({ player_id: 'p1' }),
      p2: makePlayer({ player_id: 'p2' }),
      p3: makePlayer({ player_id: 'p3' }),
      p4: makePlayer({ player_id: 'p4' }),
    }
    useGameStore.setState({ roster: Object.values(fourPlayers) })
    render(
      <LobbyScreen
        gameState={makeGameState({ players: fourPlayers })}
        hostSecret="s"
        gameId="G1"
      />
    )
    expect(screen.getByRole('button', { name: 'Need 1 more player' })).toBeInTheDocument()
  })
})
