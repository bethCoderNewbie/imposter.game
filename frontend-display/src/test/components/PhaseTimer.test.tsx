import { render, screen } from '@testing-library/react'
import PhaseTimer from '../../components/PhaseTimer/PhaseTimer'

vi.mock('../../hooks/useTimer', () => ({
  useTimer: vi.fn(() => ({ secondsRemaining: 90, isWarning: false, isCritical: false })),
}))

import { useTimer } from '../../hooks/useTimer'

describe('PhaseTimer', () => {
  it('renders MM:SS format', () => {
    render(<PhaseTimer timerEndsAt="2099-01-01T00:00:00Z" />)
    expect(screen.getByText('01:30')).toBeInTheDocument()
  })

  it('renders 00:00 when secondsRemaining is 0', () => {
    vi.mocked(useTimer).mockReturnValueOnce({ secondsRemaining: 0, isWarning: false, isCritical: false })
    render(<PhaseTimer timerEndsAt={null} />)
    expect(screen.getByText('00:00')).toBeInTheDocument()
  })

  it('applies timer--warning class', () => {
    vi.mocked(useTimer).mockReturnValueOnce({ secondsRemaining: 25, isWarning: true, isCritical: false })
    const { container } = render(<PhaseTimer timerEndsAt="2099-01-01T00:00:00Z" />)
    expect(container.querySelector('.timer--warning')).toBeInTheDocument()
  })

  it('applies timer--critical class', () => {
    vi.mocked(useTimer).mockReturnValueOnce({ secondsRemaining: 5, isWarning: true, isCritical: true })
    const { container } = render(<PhaseTimer timerEndsAt="2099-01-01T00:00:00Z" />)
    expect(container.querySelector('.timer--critical')).toBeInTheDocument()
  })

  it('applies no state class when not warning or critical', () => {
    const { container } = render(<PhaseTimer timerEndsAt="2099-01-01T00:00:00Z" />)
    expect(container.querySelector('.timer--warning')).not.toBeInTheDocument()
    expect(container.querySelector('.timer--critical')).not.toBeInTheDocument()
  })

  it('passes additional className through', () => {
    const { container } = render(<PhaseTimer timerEndsAt={null} className="night-screen__timer" />)
    expect(container.querySelector('.night-screen__timer')).toBeInTheDocument()
  })
})
