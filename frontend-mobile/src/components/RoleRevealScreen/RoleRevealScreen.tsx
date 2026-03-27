import { useState, useRef } from 'react'
import { useHaptics } from '../../hooks/useHaptics'
import { getRoleColor } from '../../types/game'
import type { PlayerState, StrippedGameState } from '../../types/game'
import './RoleRevealScreen.css'

interface Props {
  myPlayer: PlayerState
  gameState: StrippedGameState
  sendIntent: (payload: Record<string, unknown>) => void
}

/** ADR-003 §5 — DOM injection on pointerdown.
 *  Role markup is only in the DOM while the button is held.
 *  On release, role subtree is unmounted — no inspect-element leak. */
export default function RoleRevealScreen({ myPlayer, gameState, sendIntent }: Props) {
  const [isRevealing, setIsRevealing] = useState(false)
  const confirmedRef = useRef(false)
  const holdTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const { vibrate } = useHaptics()

  const role = myPlayer.role ?? 'villager'
  const roleDef = gameState.role_registry?.[role]
  const abilities = (roleDef?.abilities as string[] | undefined) ?? []
  const bgColor = getRoleColor(role)

  function handlePointerDown() {
    setIsRevealing(true)
    vibrate(200)

    // Send confirm_role_reveal after ≥1s hold (ADR-003 §5)
    if (!confirmedRef.current) {
      holdTimerRef.current = setTimeout(() => {
        sendIntent({ type: 'confirm_role_reveal' })
        confirmedRef.current = true
      }, 1000)
    }
  }

  function handlePointerUp() {
    setIsRevealing(false)
    vibrate(100)
    if (holdTimerRef.current) {
      clearTimeout(holdTimerRef.current)
      holdTimerRef.current = null
    }
  }

  return (
    <div
      className="role-reveal"
      style={isRevealing ? { backgroundColor: bgColor } : undefined}
    >
      {/* Role content — only in DOM while held (ADR-003 §5) */}
      {isRevealing && (
        <div className="role-reveal__content">
          <p className="role-reveal__label">YOU ARE THE</p>
          <h1 className="role-reveal__name">{role.replace(/_/g, ' ').toUpperCase()}</h1>
          <div className="role-reveal__icon" aria-hidden="true">
            {ROLE_ICONS[role] ?? '❓'}
          </div>
          {abilities.length > 0 && (
            <ul className="role-reveal__abilities">
              {abilities.slice(0, 3).map((ability, i) => (
                <li key={i}>{ability}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Hold button — always in DOM */}
      <button
        className={`role-reveal__hold-btn ${isRevealing ? 'role-reveal__hold-btn--active' : ''}`}
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        onPointerLeave={handlePointerUp}
      >
        {isRevealing ? 'Keep holding…' : 'HOLD TO REVEAL'}
      </button>
    </div>
  )
}

const ROLE_ICONS: Record<string, string> = {
  werewolf:      '🐺',
  alpha_wolf:    '🐺',
  wolf_shaman:   '🐺',
  seer:          '🔮',
  doctor:        '💊',
  villager:      '🏘️',
  mayor:         '🏛️',
  hunter:        '🏹',
  cupid:         '💘',
  tracker:       '🔍',
  jester:        '🃏',
  arsonist:      '🔥',
  serial_killer: '🔪',
  framer:        '🖼️',
  infector:      '🦠',
}
