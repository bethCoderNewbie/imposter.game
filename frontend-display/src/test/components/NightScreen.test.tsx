import { render, screen, act } from '@testing-library/react'
import NightScreen from '../../components/NightScreen/NightScreen'
import { makeGameState } from '../fixtures'

// Mock useTimer so component tests are not coupled to RAF/timer internals
vi.mock('../../hooks/useTimer', () => ({
  useTimer: vi.fn(() => ({ secondsRemaining: 90, isWarning: false, isCritical: false })),
}))

import { useTimer } from '../../hooks/useTimer'

beforeEach(() => {
  vi.useFakeTimers()
  vi.mocked(useTimer).mockReturnValue({ secondsRemaining: 90, isWarning: false, isCritical: false })
})

afterEach(() => {
  vi.useRealTimers()
  vi.mocked(useTimer).mockReset()
})

describe('NightScreen', () => {
  it('renders moon element', () => {
    const { container } = render(<NightScreen gameState={makeGameState({ phase: 'night' })} audioUnlocked={false} />)
    expect(container.querySelector('.night-screen__moon')).toBeInTheDocument()
  })

  it('renders formatted timer from useTimer output', () => {
    vi.mocked(useTimer).mockReturnValue({ secondsRemaining: 90, isWarning: false, isCritical: false })
    render(<NightScreen gameState={makeGameState({ phase: 'night' })} audioUnlocked={false} />)
    expect(screen.getByText('01:30')).toBeInTheDocument()
  })

  it('shows 00:00 when secondsRemaining is 0', () => {
    vi.mocked(useTimer).mockReturnValue({ secondsRemaining: 0, isWarning: false, isCritical: false })
    render(<NightScreen gameState={makeGameState({ phase: 'night' })} audioUnlocked={false} />)
    expect(screen.getByText('00:00')).toBeInTheDocument()
  })

  it('renders the first narrative text on mount', () => {
    render(<NightScreen gameState={makeGameState({ phase: 'night' })} audioUnlocked={false} />)
    expect(screen.getByText('The village sleeps…')).toBeInTheDocument()
  })

  it('rotates narrative text after 8 seconds', () => {
    render(<NightScreen gameState={makeGameState({ phase: 'night' })} audioUnlocked={false} />)
    act(() => { vi.advanceTimersByTime(8000) })
    expect(screen.getByText('Something stirs in the dark…')).toBeInTheDocument()
  })

  it('applies timer--warning class when isWarning is true', () => {
    vi.mocked(useTimer).mockReturnValue({ secondsRemaining: 25, isWarning: true, isCritical: false })
    const { container } = render(
      <NightScreen gameState={makeGameState({ phase: 'night' })} audioUnlocked={false} />
    )
    expect(container.querySelector('.timer--warning')).toBeInTheDocument()
  })

  it('applies timer--critical class when isCritical is true', () => {
    vi.mocked(useTimer).mockReturnValue({ secondsRemaining: 5, isWarning: true, isCritical: true })
    const { container } = render(
      <NightScreen gameState={makeGameState({ phase: 'night' })} audioUnlocked={false} />
    )
    expect(container.querySelector('.timer--critical')).toBeInTheDocument()
  })

  it('calls audio.play() when audioUnlocked is true', () => {
    render(<NightScreen gameState={makeGameState({ phase: 'night' })} audioUnlocked={true} />)
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled()
  })

  it('does not call audio.play() when audioUnlocked is false', () => {
    render(<NightScreen gameState={makeGameState({ phase: 'night' })} audioUnlocked={false} />)
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled()
  })
})
