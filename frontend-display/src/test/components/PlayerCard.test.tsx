import { render, screen } from '@testing-library/react'
import PlayerCard from '../../components/DayScreen/PlayerCard'
import { makePlayer } from '../fixtures'

function renderCard(
  overrides: Parameters<typeof makePlayer>[0] = {},
  voteCount = 0,
  hasMajority = false,
) {
  return render(
    <PlayerCard
      player={makePlayer(overrides)}
      voteCount={voteCount}
      hasMajority={hasMajority}
    />
  )
}

describe('PlayerCard', () => {
  it('renders player display_name', () => {
    renderCard({ display_name: 'Alice' })
    expect(screen.getByText('Alice')).toBeInTheDocument()
  })

  it('shows vote badge when voteCount > 0', () => {
    renderCard({}, 3)
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('hides vote badge when voteCount is 0', () => {
    const { container } = renderCard({}, 0)
    expect(container.querySelector('.player-card__vote-badge')).not.toBeInTheDocument()
  })

  it('adds dead class when player is not alive', () => {
    const { container } = renderCard({ is_alive: false })
    expect(container.firstElementChild).toHaveClass('player-card--dead')
  })

  it('does not add dead class when player is alive', () => {
    const { container } = renderCard({ is_alive: true })
    expect(container.firstElementChild).not.toHaveClass('player-card--dead')
  })

  it('shows tombstone SVG when player is dead', () => {
    const { container } = renderCard({ is_alive: false })
    expect(container.querySelector('.player-card__tombstone')).toBeInTheDocument()
  })

  it('does not show tombstone when player is alive', () => {
    const { container } = renderCard({ is_alive: true })
    expect(container.querySelector('.player-card__tombstone')).not.toBeInTheDocument()
  })

  it('adds majority class when hasMajority is true', () => {
    const { container } = renderCard({}, 3, true)
    expect(container.firstElementChild).toHaveClass('player-card--majority')
  })

  it('does not add majority class when hasMajority is false', () => {
    const { container } = renderCard({}, 0, false)
    expect(container.firstElementChild).not.toHaveClass('player-card--majority')
  })

  it('sets data-player-id attribute on root element', () => {
    const { container } = renderCard({ player_id: 'p99' })
    expect(container.firstElementChild).toHaveAttribute('data-player-id', 'p99')
  })
})
