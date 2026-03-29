import { WOLF_ROLES } from '../../types/game'
import type { HintPayload, PlayerState, StrippedGameState } from '../../types/game'
import FramerUI from './FramerUI'
import WolfVoteUI from './WolfVoteUI'
import SeerPeekUI from './SeerPeekUI'
import DoctorProtectUI from './DoctorProtectUI'
import TrackerUI from './TrackerUI'
import SerialKillerUI from './SerialKillerUI'
import CupidUI from './CupidUI'
import ArsonistUI from './ArsonistUI'
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
        {/* Seer and Tracker stay mounted after submission so they can display
            their result when the server broadcasts it (still in NIGHT phase). */}
        {role === 'seer' ? (
          <SeerPeekUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />
        ) : role === 'tracker' ? (
          <TrackerUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />
        ) : submitted ? (
          <p className="night-shell__waiting">Waiting for others…</p>
        ) : role === 'framer' ? (
          <FramerUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />
        ) : WOLF_ROLES.has(role) ? (
          <WolfVoteUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />
        ) : role === 'doctor' ? (
          <DoctorProtectUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />
        ) : role === 'serial_killer' ? (
          <SerialKillerUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />
        ) : role === 'cupid' && gameState.round === 1 ? (
          <CupidUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />
        ) : role === 'arsonist' ? (
          <ArsonistUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />
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
