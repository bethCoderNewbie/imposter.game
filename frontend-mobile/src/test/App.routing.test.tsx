import { render, screen, waitFor } from '@testing-library/react'
import App from '../App'
import { makeGameState, makePlayer } from './fixtures'
import type { StrippedGameState } from '../types/game'

// ── Module-level mock state ────────────────────────────────────────────────────

let mockGameState: StrippedGameState | null = null

vi.mock('../hooks/useGameState', () => ({
  useGameState: () => ({
    gameState: mockGameState,
    sendIntent: vi.fn(),
    status: 'open',
  }),
}))

vi.mock('../hooks/useHaptics', () => ({
  useHaptics: () => ({ vibrate: vi.fn() }),
}))

// ── Helpers ────────────────────────────────────────────────────────────────────

const SESSION = { game_id: 'g1', player_id: 'p1', session_token: 'tok' }

function setSession() {
  sessionStorage.setItem('ww_session', JSON.stringify(SESSION))
}

function clearSession() {
  sessionStorage.clear()
}

async function renderApp() {
  const result = render(<App />)
  // Wait for bootstrapping useEffect to resolve (fetch mock resolves synchronously)
  await waitFor(() => {
    expect(screen.queryByText('Loading…')).not.toBeInTheDocument()
  })
  return result
}

// ── Setup / teardown ───────────────────────────────────────────────────────────

beforeEach(() => {
  mockGameState = null
  clearSession()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

// ── Tests ──────────────────────────────────────────────────────────────────────

describe('App phase routing — ADR-011 Decision 4a', () => {
  it('game_over phase shows GameOverScreen even for a dead player', async () => {
    setSession()
    mockGameState = makeGameState({
      phase: 'game_over',
      winner: 'village',
      players: {
        p1: makePlayer({ player_id: 'p1', display_name: 'Alice', is_alive: false }),
        p2: makePlayer({ player_id: 'p2', display_name: 'Bob',   is_alive: true }),
      },
    })
    await renderApp()
    expect(screen.getByRole('heading', { name: 'Village Wins!' })).toBeInTheDocument()
  })

  it('game_over phase shows GameOverScreen for an alive player', async () => {
    setSession()
    mockGameState = makeGameState({
      phase: 'game_over',
      winner: 'werewolf',
    })
    await renderApp()
    expect(screen.getByRole('heading', { name: 'Wolves Win!' })).toBeInTheDocument()
  })

  it('dead player in non-game-over phase shows DeadSpectatorScreen', async () => {
    setSession()
    mockGameState = makeGameState({
      phase: 'night',
      players: {
        p1: makePlayer({ player_id: 'p1', display_name: 'Alice', is_alive: false }),
        p2: makePlayer({ player_id: 'p2', display_name: 'Bob',   is_alive: true }),
      },
    })
    await renderApp()
    // DeadSpectatorScreen should render — not GameOverScreen
    expect(screen.queryByRole('heading', { name: /Wins!/ })).not.toBeInTheDocument()
    // GameOverScreen has a "Play Again" button — dead spectator should not
    expect(screen.queryByRole('button', { name: 'Play Again' })).not.toBeInTheDocument()
  })

  it('hunter_pending phase shows HunterPendingScreen for the hunter', async () => {
    setSession()
    mockGameState = makeGameState({
      phase: 'hunter_pending',
      players: {
        p1: makePlayer({ player_id: 'p1', display_name: 'Alice', is_alive: true, role: 'hunter' }),
        p2: makePlayer({ player_id: 'p2', display_name: 'Bob',   is_alive: true }),
      },
    })
    await renderApp()
    expect(screen.getByText('You have been eliminated — take your revenge.')).toBeInTheDocument()
  })
})
