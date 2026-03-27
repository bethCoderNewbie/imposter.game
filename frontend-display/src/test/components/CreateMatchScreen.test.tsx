import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CreateMatchScreen from '../../components/CreateMatchScreen/CreateMatchScreen'

function mockFetch(response: { ok: boolean; json?: object }) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: response.ok,
    json: () => Promise.resolve(response.json ?? {}),
  }))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('CreateMatchScreen', () => {
  it('renders Create New Match button in enabled state', () => {
    render(<CreateMatchScreen onCreated={vi.fn()} />)
    const btn = screen.getByRole('button', { name: /create new match/i })
    expect(btn).toBeEnabled()
  })

  it('disables button while fetch is in flight', async () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {}))) // never resolves
    render(<CreateMatchScreen onCreated={vi.fn()} />)
    await userEvent.click(screen.getByRole('button'))
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('calls onCreated with game_id and host_secret on 200', async () => {
    mockFetch({ ok: true, json: { game_id: 'ABC123', host_secret: 'secret-xyz', join_code: 'ABC123' } })
    const onCreated = vi.fn()
    render(<CreateMatchScreen onCreated={onCreated} />)
    await userEvent.click(screen.getByRole('button'))
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith('ABC123', 'secret-xyz'))
  })

  it('shows server error message on 4xx with detail field', async () => {
    mockFetch({ ok: false, json: { detail: 'Server full' } })
    render(<CreateMatchScreen onCreated={vi.fn()} />)
    await userEvent.click(screen.getByRole('button'))
    await waitFor(() => expect(screen.getByText('Server full')).toBeInTheDocument())
  })

  it('shows generic error message on 4xx with no detail', async () => {
    mockFetch({ ok: false, json: {} })
    render(<CreateMatchScreen onCreated={vi.fn()} />)
    await userEvent.click(screen.getByRole('button'))
    await waitFor(() =>
      expect(screen.getByText(/could not create game/i)).toBeInTheDocument()
    )
  })

  it('shows network error message when fetch rejects', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('NetworkError')))
    render(<CreateMatchScreen onCreated={vi.fn()} />)
    await userEvent.click(screen.getByRole('button'))
    await waitFor(() =>
      expect(screen.getByText(/network error/i)).toBeInTheDocument()
    )
  })

  it('re-enables button after an error', async () => {
    mockFetch({ ok: false, json: {} })
    render(<CreateMatchScreen onCreated={vi.fn()} />)
    await userEvent.click(screen.getByRole('button'))
    await waitFor(() => expect(screen.getByRole('button')).toBeEnabled())
  })

  it('does not submit a second time while loading (button is disabled)', async () => {
    // Fetch never resolves — keeps loading=true indefinitely
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})))
    render(<CreateMatchScreen onCreated={vi.fn()} />)
    await userEvent.click(screen.getByRole('button'))
    // Button should now be disabled
    expect(screen.getByRole('button')).toBeDisabled()
    // Clicking a disabled button is a no-op
    await userEvent.click(screen.getByRole('button'))
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1)
  })
})
