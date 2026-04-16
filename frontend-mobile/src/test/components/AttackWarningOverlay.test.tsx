import { render, screen, fireEvent } from '@testing-library/react'
import AttackWarningOverlay from '../../components/NightActionShell/AttackWarningOverlay'

describe('AttackWarningOverlay', () => {
  it('renders a DEFEND button', () => {
    render(<AttackWarningOverlay sendIntent={vi.fn()} />)
    expect(screen.getByRole('button', { name: /defend/i })).toBeInTheDocument()
  })

  it('clicking DEFEND sends a grid_defend intent', () => {
    const sendIntent = vi.fn()
    render(<AttackWarningOverlay sendIntent={sendIntent} />)
    fireEvent.click(screen.getByRole('button', { name: /defend/i }))
    expect(sendIntent).toHaveBeenCalledOnce()
    expect(sendIntent).toHaveBeenCalledWith({ type: 'grid_defend' })
  })

  it('sends exactly one intent per click', () => {
    const sendIntent = vi.fn()
    render(<AttackWarningOverlay sendIntent={sendIntent} />)
    const btn = screen.getByRole('button', { name: /defend/i })
    fireEvent.click(btn)
    fireEvent.click(btn)
    expect(sendIntent).toHaveBeenCalledTimes(2)
  })
})
