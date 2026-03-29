import { render, screen } from '@testing-library/react'
import NightActionShell from '../../components/NightActionShell/NightActionShell'
import { makeGameState, makePlayer } from '../fixtures'

vi.mock('../../hooks/useHaptics', () => ({
  useHaptics: () => ({ vibrate: vi.fn() }),
}))

function renderShell(role: string, round = 1) {
  const myPlayer = makePlayer({ player_id: 'p1', role })
  const gameState = makeGameState({ round })
  return render(
    <NightActionShell
      gameState={gameState}
      myPlayer={myPlayer}
      sendIntent={vi.fn()}
    />
  )
}

describe('NightActionShell role routing', () => {
  it('tracker role → TrackerUI ("Choose who to follow")', () => {
    renderShell('tracker')
    expect(screen.getByText('Choose who to follow')).toBeInTheDocument()
  })

  it('serial_killer role → SerialKillerUI ("Choose your target")', () => {
    renderShell('serial_killer')
    expect(screen.getByText('Choose your target')).toBeInTheDocument()
  })

  it('cupid role in round 1 → CupidUI ("Choose the first lover")', () => {
    renderShell('cupid', 1)
    expect(screen.getByText('Choose the first lover')).toBeInTheDocument()
  })

  it('cupid role in round 2+ → VillagerDecoyUI (no action after round 1)', () => {
    renderShell('cupid', 2)
    expect(screen.getByText('The Archives await…')).toBeInTheDocument()
  })

  it('arsonist role → ArsonistUI ("Choose who to douse")', () => {
    renderShell('arsonist')
    expect(screen.getByText('Choose who to douse')).toBeInTheDocument()
  })

  it('villager role → VillagerDecoyUI fallback', () => {
    renderShell('villager')
    expect(screen.getByText('The Archives await…')).toBeInTheDocument()
  })

  it('submitted player sees waiting message regardless of role', () => {
    const myPlayer = makePlayer({ player_id: 'p1', role: 'tracker', night_action_submitted: true })
    const gameState = makeGameState()
    render(
      <NightActionShell
        gameState={gameState}
        myPlayer={myPlayer}
        sendIntent={vi.fn()}
      />
    )
    expect(screen.getByText('Waiting for others…')).toBeInTheDocument()
  })
})
