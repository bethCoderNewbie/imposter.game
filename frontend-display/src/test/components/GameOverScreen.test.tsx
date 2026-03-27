import { render, screen } from '@testing-library/react'
import GameOverScreen from '../../components/GameOverScreen/GameOverScreen'
import { makeGameState, makePlayer } from '../fixtures'
import type { PostMatch } from '../../types/game'

afterEach(() => {
  document.documentElement.className = ''
})

describe('GameOverScreen', () => {
  it('shows village victory headline', () => {
    render(
      <GameOverScreen gameState={makeGameState({ winner: 'village' })} audioUnlocked={false} />
    )
    expect(screen.getByText('THE VILLAGE SURVIVES')).toBeInTheDocument()
  })

  it('shows wolf victory headline', () => {
    render(
      <GameOverScreen gameState={makeGameState({ winner: 'werewolf' })} audioUnlocked={false} />
    )
    expect(screen.getByText('THE WOLVES DEVOUR THE VILLAGE')).toBeInTheDocument()
  })

  it('sets winner-village class on documentElement for village win', () => {
    render(
      <GameOverScreen gameState={makeGameState({ winner: 'village' })} audioUnlocked={false} />
    )
    expect(document.documentElement).toHaveClass('winner-village')
  })

  it('sets winner-wolf class on documentElement for wolf win', () => {
    render(
      <GameOverScreen gameState={makeGameState({ winner: 'werewolf' })} audioUnlocked={false} />
    )
    expect(document.documentElement).toHaveClass('winner-wolf')
  })

  it('clears documentElement class on unmount', () => {
    const { unmount } = render(
      <GameOverScreen gameState={makeGameState({ winner: 'village' })} audioUnlocked={false} />
    )
    unmount()
    expect(document.documentElement.className).toBe('')
  })

  it('renders each player name', () => {
    render(
      <GameOverScreen gameState={makeGameState({ winner: 'village' })} audioUnlocked={false} />
    )
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getByText('Bob')).toBeInTheDocument()
    expect(screen.getByText('Carol')).toBeInTheDocument()
  })

  it('shows role badge when player.role is set', () => {
    const players = {
      p1: makePlayer({ player_id: 'p1', display_name: 'Alice', role: 'werewolf' }),
    }
    render(
      <GameOverScreen gameState={makeGameState({ winner: 'village', players })} audioUnlocked={false} />
    )
    expect(screen.getByText('werewolf')).toBeInTheDocument()
  })

  it('omits role badge when player.role is null', () => {
    const players = {
      p1: makePlayer({ player_id: 'p1', display_name: 'Alice', role: null }),
    }
    const { container } = render(
      <GameOverScreen gameState={makeGameState({ winner: 'village', players })} audioUnlocked={false} />
    )
    expect(container.querySelector('.game-over__role-badge')).not.toBeInTheDocument()
  })

  it('renders timeline entries when post_match is present', () => {
    const postMatch: PostMatch = {
      timeline: [
        { round: 1, phase: 'night', event_type: 'kill', actor_id: 'p1', target_id: 'p2', display_text: 'Wolf killed Bob' },
        { round: 1, phase: 'day', event_type: 'vote', actor_id: null, target_id: 'p3', display_text: 'Village voted out Carol' },
      ],
      winner: 'village',
      rounds_played: 1,
    }
    render(
      <GameOverScreen
        gameState={makeGameState({ winner: 'village', post_match: postMatch })}
        audioUnlocked={false}
      />
    )
    expect(screen.getByText('Wolf killed Bob')).toBeInTheDocument()
    expect(screen.getByText('Village voted out Carol')).toBeInTheDocument()
  })

  it('hides timeline section when post_match is null', () => {
    const { container } = render(
      <GameOverScreen
        gameState={makeGameState({ winner: 'village', post_match: null })}
        audioUnlocked={false}
      />
    )
    expect(container.querySelector('.game-over__timeline')).not.toBeInTheDocument()
  })

  it('plays audio when audioUnlocked is true', () => {
    render(
      <GameOverScreen gameState={makeGameState({ winner: 'village' })} audioUnlocked={true} />
    )
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled()
  })
})
