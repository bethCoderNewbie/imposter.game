import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CreateMatchScreen from '../../components/CreateMatchScreen/CreateMatchScreen'

function mockFetch(responses: Array<{ ok: boolean; json?: object }>) {
  let callIndex = 0
  vi.stubGlobal('fetch', vi.fn().mockImplementation(() => {
    const resp = responses[callIndex] ?? responses[responses.length - 1]
    callIndex++
    return Promise.resolve({
      ok: resp.ok,
      json: () => Promise.resolve(resp.json ?? {}),
    })
  }))
}

/** Helper: stub both POST /api/games and PATCH /api/games/{id}/config */
function mockCreateSuccess(gameId = 'ABC123', hostSecret = 'secret-xyz') {
  mockFetch([
    { ok: true, json: { game_id: gameId, host_secret: hostSecret, join_code: gameId } },
    { ok: true, json: { ok: true } },
  ])
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('CreateMatchScreen', () => {
  // ── Core create flow ─────────────────────────────────────────────────────────

  it('renders Create New Match button in enabled state', () => {
    render(<CreateMatchScreen onCreated={vi.fn()} onResumed={vi.fn()} />)
    const btn = screen.getByRole('button', { name: /create new match/i })
    expect(btn).toBeEnabled()
  })

  it('disables button while fetch is in flight', async () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {}))) // never resolves
    render(<CreateMatchScreen onCreated={vi.fn()} onResumed={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /create new match/i }))
    expect(screen.getByRole('button', { name: /creating/i })).toBeDisabled()
  })

  it('calls onCreated with game_id and host_secret on 200', async () => {
    mockCreateSuccess('ABC123', 'secret-xyz')
    const onCreated = vi.fn()
    render(<CreateMatchScreen onCreated={onCreated} onResumed={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /create new match/i }))
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith('ABC123', 'secret-xyz'))
  })

  it('shows server error message on 4xx with detail field', async () => {
    mockFetch([{ ok: false, json: { detail: 'Server full' } }])
    render(<CreateMatchScreen onCreated={vi.fn()} onResumed={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /create new match/i }))
    await waitFor(() => expect(screen.getByText('Server full')).toBeInTheDocument())
  })

  it('shows generic error message on 4xx with no detail', async () => {
    mockFetch([{ ok: false, json: {} }])
    render(<CreateMatchScreen onCreated={vi.fn()} onResumed={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /create new match/i }))
    await waitFor(() =>
      expect(screen.getByText(/could not create game/i)).toBeInTheDocument()
    )
  })

  it('shows network error message when fetch rejects', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('NetworkError')))
    render(<CreateMatchScreen onCreated={vi.fn()} onResumed={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /create new match/i }))
    await waitFor(() =>
      expect(screen.getByText(/network error/i)).toBeInTheDocument()
    )
  })

  it('re-enables button after an error', async () => {
    mockFetch([{ ok: false, json: {} }])
    render(<CreateMatchScreen onCreated={vi.fn()} onResumed={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /create new match/i }))
    await waitFor(() => expect(screen.getByRole('button', { name: /create new match/i })).toBeEnabled())
  })

  it('does not submit a second time while loading (button is disabled)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})))
    render(<CreateMatchScreen onCreated={vi.fn()} onResumed={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /create new match/i }))
    expect(screen.getByRole('button', { name: /creating/i })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: /creating/i }))
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1)
  })

  // ── Pre-game settings UI ─────────────────────────────────────────────────────

  it('renders difficulty selector with three options', () => {
    render(<CreateMatchScreen onCreated={vi.fn()} onResumed={vi.fn()} />)
    expect(screen.getByRole('button', { name: /easy/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /balanced/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /hard/i })).toBeInTheDocument()
  })

  it('renders phase timer steppers for Night, Day, and Vote', () => {
    render(<CreateMatchScreen onCreated={vi.fn()} onResumed={vi.fn()} />)
    expect(screen.getByText('Night')).toBeInTheDocument()
    expect(screen.getByText('Day')).toBeInTheDocument()
    expect(screen.getByText('Vote')).toBeInTheDocument()
  })

  it('changes active difficulty when a difficulty button is clicked', async () => {
    render(<CreateMatchScreen onCreated={vi.fn()} onResumed={vi.fn()} />)
    const hardBtn = screen.getByRole('button', { name: /hard/i })
    await userEvent.click(hardBtn)
    expect(hardBtn).toHaveClass('create-match__difficulty-btn--active')
  })

  // ── PATCH is called after game creation ──────────────────────────────────────

  it('calls PATCH /api/games/{id}/config after game creation', async () => {
    mockCreateSuccess('GAME01', 'host-secret')
    render(<CreateMatchScreen onCreated={vi.fn()} onResumed={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /create new match/i }))

    await waitFor(() => {
      const fetchMock = vi.mocked(fetch)
      expect(fetchMock).toHaveBeenCalledTimes(2)
      const patchCall = fetchMock.mock.calls[1]
      expect(patchCall[0]).toBe('/api/games/GAME01/config')
      expect((patchCall[1] as RequestInit).method).toBe('PATCH')
    })
  })

  it('sends selected difficulty in PATCH body', async () => {
    mockCreateSuccess('GAME01', 'host-secret')
    render(<CreateMatchScreen onCreated={vi.fn()} onResumed={vi.fn()} />)

    // Switch to Hard
    await userEvent.click(screen.getByRole('button', { name: /hard/i }))
    await userEvent.click(screen.getByRole('button', { name: /create new match/i }))

    await waitFor(() => {
      const patchCall = vi.mocked(fetch).mock.calls[1]
      const body = JSON.parse((patchCall[1] as RequestInit).body as string)
      expect(body.difficulty_level).toBe('hard')
      expect(body.host_secret).toBe('host-secret')
    })
  })

  it('sends host_secret in PATCH body', async () => {
    mockCreateSuccess('GAME01', 'my-secret')
    render(<CreateMatchScreen onCreated={vi.fn()} onResumed={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /create new match/i }))

    await waitFor(() => {
      const patchCall = vi.mocked(fetch).mock.calls[1]
      const body = JSON.parse((patchCall[1] as RequestInit).body as string)
      expect(body.host_secret).toBe('my-secret')
    })
  })
})
