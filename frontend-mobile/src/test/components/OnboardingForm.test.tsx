import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import OnboardingForm from '../../components/OnboardingForm/OnboardingForm'

// ── Fetch helpers ─────────────────────────────────────────────────────────────

type MockResp = { status: number; json?: object }

function mockFetchSequence(responses: MockResp[]) {
  let idx = 0
  vi.stubGlobal('fetch', vi.fn().mockImplementation(() => {
    const resp = responses[idx] ?? responses[responses.length - 1]
    idx++
    return Promise.resolve({
      ok: resp.status >= 200 && resp.status < 300,
      status: resp.status,
      json: () => Promise.resolve(resp.json ?? {}),
    })
  }))
}

function mockFetch(resp: MockResp) {
  mockFetchSequence([resp])
}

// ── localStorage helper ───────────────────────────────────────────────────────

function setStoredSession(game_id: string, session_token = 'stored-tok') {
  localStorage.setItem('ww_session', JSON.stringify({ game_id, player_id: 'pid-1', session_token }))
}

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('OnboardingForm', () => {
  // ── Join mode (default) ────────────────────────────────────────────────────

  it('renders join form by default', () => {
    render(<OnboardingForm prefillCode="" onJoined={vi.fn()} />)
    expect(screen.getByRole('button', { name: /join game/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /rejoin game/i })).not.toBeInTheDocument()
  })

  it('pre-fills game code from prefillCode prop', () => {
    render(<OnboardingForm prefillCode="abc123" onJoined={vi.fn()} />)
    expect(screen.getByDisplayValue('ABC123')).toBeInTheDocument()
  })

  it('calls onJoined with session data on successful join', async () => {
    mockFetch({ status: 200, json: { game_id: 'G1', player_id: 'p1', session_token: 'tok' } })
    const onJoined = vi.fn()
    render(<OnboardingForm prefillCode="G1" onJoined={onJoined} />)
    await userEvent.type(screen.getByLabelText(/your name/i), 'Alice')
    await userEvent.click(screen.getByRole('button', { name: /join game/i }))
    await waitFor(() => expect(onJoined).toHaveBeenCalledWith({ game_id: 'G1', player_id: 'p1', session_token: 'tok' }))
  })

  it('shows server error on non-409 failure', async () => {
    mockFetch({ status: 404, json: { detail: 'Game not found.' } })
    render(<OnboardingForm prefillCode="" onJoined={vi.fn()} />)
    await userEvent.type(screen.getByLabelText(/your name/i), 'Alice')
    await userEvent.type(screen.getByLabelText(/game code/i), 'NOPE')
    await userEvent.click(screen.getByRole('button', { name: /join game/i }))
    await waitFor(() => expect(screen.getByText('Game not found.')).toBeInTheDocument())
  })

  // ── 409 → auto-switch to rejoin ────────────────────────────────────────────

  it('switches to rejoin mode when JOIN returns 409', async () => {
    mockFetch({ status: 409, json: { detail: 'Game already started.' } })
    render(<OnboardingForm prefillCode="GAME1" onJoined={vi.fn()} />)
    await userEvent.type(screen.getByLabelText(/your name/i), 'Alice')
    await userEvent.click(screen.getByRole('button', { name: /join game/i }))
    await waitFor(() => expect(screen.getByRole('button', { name: /rejoin game/i })).toBeInTheDocument())
    expect(screen.getByText(/game already started/i)).toBeInTheDocument()
  })

  it('pre-fills rejoin code with the join code when switching on 409', async () => {
    mockFetch({ status: 409 })
    render(<OnboardingForm prefillCode="GAME1" onJoined={vi.fn()} />)
    await userEvent.type(screen.getByLabelText(/your name/i), 'Alice')
    await userEvent.click(screen.getByRole('button', { name: /join game/i }))
    await waitFor(() => expect(screen.getByRole('button', { name: /rejoin game/i })).toBeInTheDocument())
    expect(screen.getByDisplayValue('GAME1')).toBeInTheDocument()
  })

  it('auto-rejoins silently when 409 and stored session matches game code', async () => {
    setStoredSession('GAME1', 'my-stored-token')
    // First call: JOIN → 409; second call: REJOIN with stored token → 200
    mockFetchSequence([
      { status: 409 },
      { status: 200, json: { game_id: 'GAME1', player_id: 'p1', session_token: 'my-stored-token' } },
    ])
    const onJoined = vi.fn()
    render(<OnboardingForm prefillCode="GAME1" onJoined={onJoined} />)
    await userEvent.type(screen.getByLabelText(/your name/i), 'Alice')
    await userEvent.click(screen.getByRole('button', { name: /join game/i }))
    await waitFor(() => expect(onJoined).toHaveBeenCalledWith(
      expect.objectContaining({ game_id: 'GAME1', session_token: 'my-stored-token' })
    ))
    // Should NOT switch to rejoin UI since auto-rejoin succeeded
    expect(screen.queryByRole('button', { name: /rejoin game/i })).not.toBeInTheDocument()
  })

  it('shows rejoin mode if 409 occurs and stored session auto-rejoin fails', async () => {
    setStoredSession('GAME1', 'stale-token')
    mockFetchSequence([
      { status: 409 },   // JOIN
      { status: 401 },   // auto-rejoin with stored token → fail
    ])
    render(<OnboardingForm prefillCode="GAME1" onJoined={vi.fn()} />)
    await userEvent.type(screen.getByLabelText(/your name/i), 'Alice')
    await userEvent.click(screen.getByRole('button', { name: /join game/i }))
    await waitFor(() => expect(screen.getByRole('button', { name: /rejoin game/i })).toBeInTheDocument())
  })

  // ── Manual rejoin mode ─────────────────────────────────────────────────────

  it('shows rejoin form when "Returning player?" link is clicked', async () => {
    render(<OnboardingForm prefillCode="" onJoined={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /returning player/i }))
    expect(screen.getByRole('button', { name: /rejoin game/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/session token/i)).toBeInTheDocument()
  })

  it('calls onJoined on successful rejoin', async () => {
    mockFetch({ status: 200, json: { game_id: 'G1', player_id: 'p99', session_token: 'valid-tok' } })
    const onJoined = vi.fn()
    render(<OnboardingForm prefillCode="G1" onJoined={onJoined} />)
    await userEvent.click(screen.getByRole('button', { name: /returning player/i }))
    await userEvent.type(screen.getByLabelText(/session token/i), 'valid-tok')
    await userEvent.click(screen.getByRole('button', { name: /rejoin game/i }))
    await waitFor(() => expect(onJoined).toHaveBeenCalledWith(
      expect.objectContaining({ game_id: 'G1', session_token: 'valid-tok' })
    ))
  })

  it('shows error on rejoin 401', async () => {
    mockFetch({ status: 401, json: { detail: 'Invalid or expired session token.' } })
    render(<OnboardingForm prefillCode="" onJoined={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /returning player/i }))
    await userEvent.type(screen.getByLabelText(/session token/i), 'bad-token')
    await userEvent.type(screen.getByLabelText(/game code/i), 'GAME1')
    await userEvent.click(screen.getByRole('button', { name: /rejoin game/i }))
    await waitFor(() => expect(screen.getByText(/invalid session token/i)).toBeInTheDocument())
  })

  it('can switch back to join mode from rejoin mode', async () => {
    render(<OnboardingForm prefillCode="" onJoined={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /returning player/i }))
    expect(screen.getByRole('button', { name: /rejoin game/i })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /join a new game instead/i }))
    expect(screen.getByRole('button', { name: /join game/i })).toBeInTheDocument()
  })

  it('disables rejoin button until both code and token are filled', async () => {
    render(<OnboardingForm prefillCode="" onJoined={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /returning player/i }))
    expect(screen.getByRole('button', { name: /rejoin game/i })).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/game code/i), 'GAME1')
    expect(screen.getByRole('button', { name: /rejoin game/i })).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/session token/i), 'tok')
    expect(screen.getByRole('button', { name: /rejoin game/i })).toBeEnabled()
  })
})
