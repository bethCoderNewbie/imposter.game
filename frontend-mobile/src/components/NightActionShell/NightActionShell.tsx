import { WOLF_ROLES } from '../../types/game'
import type { HintPayload, PlayerState, StrippedGameState } from '../../types/game'
import WolfVoteUI from './WolfVoteUI'
import SeerPeekUI from './SeerPeekUI'
import DoctorProtectUI from './DoctorProtectUI'
import VillagerDecoyUI from './VillagerDecoyUI'
import './NightActionShell.css'

interface Props {
  gameState: StrippedGameState
  myPlayer: PlayerState
  sendIntent: (payload: Record<string, unknown>) => void
  latestHint?: HintPayload | null
}

export default function NightActionShell({ gameState, myPlayer, sendIntent, latestHint }: Props) {
  const role = myPlayer.role ?? 'villager'
  const submitted = myPlayer.night_action_submitted

  return (
    <div className="night-shell">
      <div className="night-shell__label">
        <span className="night-shell__moon">🌙</span> Night
      </div>

      <div className="night-shell__content">
        {submitted ? (
          <p className="night-shell__waiting">Waiting for others…</p>
        ) : WOLF_ROLES.has(role) ? (
          <WolfVoteUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />
        ) : role === 'seer' ? (
          <SeerPeekUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />
        ) : role === 'doctor' ? (
          <DoctorProtectUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />
        ) : (
          <VillagerDecoyUI
            gameState={gameState}
            myPlayer={myPlayer}
            sendIntent={sendIntent}
            latestHint={latestHint}
          />
        )}
      </div>
    </div>
  )
}
