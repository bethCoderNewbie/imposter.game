import { render, screen } from '@testing-library/react'
import PlayerAvatar from '../../components/PlayerAvatar/PlayerAvatar'
import { makePlayer } from '../fixtures'

describe('PlayerAvatar', () => {
  it('renders first two chars of display_name as initials (uppercase)', () => {
    render(<PlayerAvatar player={makePlayer({ display_name: 'Alice' })} />)
    expect(screen.getByText('AL')).toBeInTheDocument()
  })

  it('handles single-char display_name without crash', () => {
    render(<PlayerAvatar player={makePlayer({ display_name: 'X' })} />)
    expect(screen.getByText('X')).toBeInTheDocument()
  })

  it('applies background color for known avatar_id', () => {
    const { container } = render(
      <PlayerAvatar player={makePlayer({ avatar_id: 'avatar_01' })} />
    )
    expect(container.firstElementChild).toHaveStyle({ backgroundColor: '#e57373' })
  })

  it('falls back to grey (#718096) for unknown avatar_id', () => {
    const { container } = render(
      <PlayerAvatar player={makePlayer({ avatar_id: 'avatar_99' })} />
    )
    expect(container.firstElementChild).toHaveStyle({ backgroundColor: '#718096' })
  })

  it('applies width and height when size prop is given', () => {
    const { container } = render(
      <PlayerAvatar player={makePlayer()} size={96} />
    )
    expect(container.firstElementChild).toHaveStyle({ width: '96px', height: '96px' })
  })

  it('applies className prop to root element', () => {
    const { container } = render(
      <PlayerAvatar player={makePlayer()} className="my-class" />
    )
    expect(container.firstElementChild).toHaveClass('my-class')
  })

  it('sets data-player-id from player.player_id by default', () => {
    const { container } = render(
      <PlayerAvatar player={makePlayer({ player_id: 'p42' })} />
    )
    expect(container.firstElementChild).toHaveAttribute('data-player-id', 'p42')
  })

  it('overrides data-player-id via explicit prop', () => {
    const { container } = render(
      <PlayerAvatar player={makePlayer({ player_id: 'p42' })} data-player-id="custom-id" />
    )
    expect(container.firstElementChild).toHaveAttribute('data-player-id', 'custom-id')
  })
})
