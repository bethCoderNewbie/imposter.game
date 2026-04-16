import { render, screen } from '@testing-library/react'
import NightActionShell from '../../components/NightActionShell/NightActionShell'
import { makeGameState, makePlayer } from '../fixtures'

// Mock hooks used by child role components
vi.mock('../../hooks/useHaptics', () => ({
  useHaptics: () => ({ vibrate: vi.fn() }),
}))
vi.spyOn(window, 'requestAnimationFrame').mockImplementation(() => 0)
vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => undefined)

function renderShell(
  role: string,
  underAttack: boolean | undefined,
  submitted = false
) {
  const myPlayer = makePlayer({
    player_id: 'p1',
    role,
    night_action_submitted: submitted,
    under_attack: underAttack,
  })
  const gameState = makeGameState({ phase: 'night' })
  return render(
    <NightActionShell
      gameState={gameState}
      myPlayer={myPlayer}
      sendIntent={vi.fn()}
    />
  )
}

describe('NightActionShell — AttackWarningOverlay visibility', () => {

  // ── Should show DEFEND ──────────────────────────────────────────────────────

  it('shows DEFEND for plain villager when under_attack=true', () => {
    renderShell('villager', true)
    expect(screen.getByRole('button', { name: /defend/i })).toBeInTheDocument()
  })

  it('shows DEFEND for doctor when under_attack=true', () => {
    renderShell('doctor', true)
    expect(screen.getByRole('button', { name: /defend/i })).toBeInTheDocument()
  })

  it('shows DEFEND for seer when under_attack=true', () => {
    renderShell('seer', true)
    expect(screen.getByRole('button', { name: /defend/i })).toBeInTheDocument()
  })

  it('shows DEFEND for tracker when under_attack=true', () => {
    renderShell('tracker', true)
    expect(screen.getByRole('button', { name: /defend/i })).toBeInTheDocument()
  })

  it('shows DEFEND for bodyguard when under_attack=true', () => {
    renderShell('bodyguard', true)
    expect(screen.getByRole('button', { name: /defend/i })).toBeInTheDocument()
  })

  it('shows DEFEND when player has submitted (Waiting screen) and under_attack=true', () => {
    renderShell('tracker', true, /* submitted= */ true)
    expect(screen.getByRole('button', { name: /defend/i })).toBeInTheDocument()
  })

  // ── Should NOT show DEFEND ──────────────────────────────────────────────────

  it('hides DEFEND for villager when under_attack=false', () => {
    renderShell('villager', false)
    expect(screen.queryByRole('button', { name: /defend/i })).not.toBeInTheDocument()
  })

  it('hides DEFEND for villager when under_attack=undefined', () => {
    renderShell('villager', undefined)
    expect(screen.queryByRole('button', { name: /defend/i })).not.toBeInTheDocument()
  })

  it('does NOT show DEFEND for werewolf role even if under_attack=true', () => {
    renderShell('werewolf', true)
    expect(screen.queryByRole('button', { name: /defend/i })).not.toBeInTheDocument()
  })

  it('does NOT show DEFEND for alpha_wolf role even if under_attack=true', () => {
    renderShell('alpha_wolf', true)
    expect(screen.queryByRole('button', { name: /defend/i })).not.toBeInTheDocument()
  })

  it('does NOT show DEFEND for framer role even if under_attack=true', () => {
    renderShell('framer', true)
    expect(screen.queryByRole('button', { name: /defend/i })).not.toBeInTheDocument()
  })

  // ── DEFEND does not interfere with role UI ─────────────────────────────────

  it('DEFEND coexists with Waiting text when submitted and under_attack=true', () => {
    renderShell('tracker', true, /* submitted= */ true)
    expect(screen.getByText(/waiting for others/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /defend/i })).toBeInTheDocument()
  })

  it('DEFEND coexists with villager archive UI when under_attack=true', () => {
    renderShell('villager', true)
    expect(screen.getByText(/archives await/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /defend/i })).toBeInTheDocument()
  })
})
