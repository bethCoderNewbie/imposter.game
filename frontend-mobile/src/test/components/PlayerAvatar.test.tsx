import { render, screen } from '@testing-library/react'
import PlayerAvatar from '../../components/PlayerAvatar/PlayerAvatar'
import { makePlayer } from '../fixtures'
import { AVATAR_COLORS } from '../../types/game'

describe('PlayerAvatar', () => {
  it('renders initials from display_name', () => {
    const player = makePlayer({ display_name: 'Alice' })
    const { container } = render(<PlayerAvatar player={player} />)
    expect(container.firstChild).toHaveTextContent('AL')
  })

  it('applies background color from avatar_id', () => {
    const player = makePlayer({ avatar_id: 'avatar_01' })
    const { container } = render(<PlayerAvatar player={player} />)
    expect(container.firstChild).toHaveStyle({ backgroundColor: AVATAR_COLORS['avatar_01'] })
  })

  it('falls back to #718096 for unknown avatar_id', () => {
    const player = makePlayer({ avatar_id: 'avatar_unknown' })
    const { container } = render(<PlayerAvatar player={player} />)
    expect(container.firstChild).toHaveStyle({ backgroundColor: '#718096' })
  })

  it('applies size prop as width, height, and derived fontSize', () => {
    const player = makePlayer()
    const { container } = render(<PlayerAvatar player={player} size={32} />)
    const el = container.firstChild as HTMLElement
    expect(el.style.width).toBe('32px')
    expect(el.style.height).toBe('32px')
    expect(el.style.fontSize).toBe(`${32 * 0.38}px`)
  })

  it('merges style prop onto container', () => {
    const player = makePlayer()
    const { container } = render(<PlayerAvatar player={player} style={{ filter: 'grayscale(1)' }} />)
    expect(container.firstChild).toHaveStyle({ filter: 'grayscale(1)' })
  })

  it('appends className to player-avatar', () => {
    const player = makePlayer()
    const { container } = render(<PlayerAvatar player={player} className="custom-class" />)
    expect(container.firstChild).toHaveClass('player-avatar', 'custom-class')
  })

  it('sets aria-label to display_name and role img', () => {
    const player = makePlayer({ display_name: 'Alice' })
    render(<PlayerAvatar player={player} />)
    expect(screen.getByRole('img', { name: 'Alice' })).toBeInTheDocument()
  })
})
