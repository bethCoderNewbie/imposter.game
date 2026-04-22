import { useState } from 'react'
import { WOLF_ROLES } from '../../types/game'
import type { GridRippleMessage, HintPayload, PlayerState, StrippedGameState } from '../../types/game'
import Tooltip from '../Tooltip/Tooltip'
import {
  TOOLTIP_GRID_OVERVIEW,
  TOOLTIP_RADAR_OVERVIEW,
} from '../Tooltip/Tooltip.constants'
import FramerUI from './FramerUI'
import WolfVoteUI from './WolfVoteUI'
import SeerPeekUI from './SeerPeekUI'
import DoctorProtectUI from './DoctorProtectUI'
import TrackerUI from './TrackerUI'
import SerialKillerUI from './SerialKillerUI'
import CupidUI from './CupidUI'
import ArsonistUI from './ArsonistUI'
import WitchUI from './WitchUI'
import LunaticUI from './LunaticUI'
import BodyguardUI from './BodyguardUI'
import VillagerDecoyUI from './VillagerDecoyUI'
import GridMapUI from './GridMapUI'
import WolfRadarUI from './WolfRadarUI'
import AttackWarningOverlay from './AttackWarningOverlay'
import './NightActionShell.css'

interface Props {
  gameState: StrippedGameState
  myPlayer: PlayerState
  sendIntent: (payload: Record<string, unknown>) => void
  latestArchiveHint?: HintPayload | null
  latestGridHint?: HintPayload | null
  latestRipple?: GridRippleMessage | null
}

type VillagerTab = 'archive' | 'grid'
type WolfTab = 'vote' | 'radar'

export default function NightActionShell({ gameState, myPlayer, sendIntent, latestArchiveHint, latestGridHint, latestRipple }: Props) {
  const role = myPlayer.role ?? 'villager'
  const submitted = myPlayer.night_action_submitted
  const [villagerTab, setVillagerTab] = useState<VillagerTab>('archive')
  const [wolfTab, setWolfTab] = useState<WolfTab>('vote')

  const nightActions = gameState.night_actions
  const wolfTeammates = WOLF_ROLES.has(role)
    ? Object.values(gameState.players).filter(
        p => p.is_alive && p.player_id !== myPlayer.player_id && p.team === 'werewolf',
      )
    : []

  return (
    <div className="night-shell">
      <div className="night-shell__label">
        <span className="night-shell__moon">🌙</span> Night
      </div>

      <div className="night-shell__content">
        {/* Defend button — shown for any non-wolf when a wolf charges their quadrant.
            Lives here (not inside role branches) so it works for all roles and for
            players showing "Waiting for others…". */}
        {!WOLF_ROLES.has(role) && myPlayer.under_attack && (
          <AttackWarningOverlay sendIntent={sendIntent} />
        )}

        {/* Seer and Tracker stay mounted after submission so they can display
            their result when the server broadcasts it (still in NIGHT phase). */}
        {role === 'seer' ? (
          <SeerPeekUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />
        ) : role === 'tracker' ? (
          <TrackerUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />
        ) : submitted && !WOLF_ROLES.has(role) ? (
          <p className="night-shell__waiting">Waiting for others…</p>
        ) : WOLF_ROLES.has(role) ? (
          /* All wolf-team roles (werewolf, alpha_wolf, wolf_shaman, framer, infector)
             get HUNT + RADAR tabs. The HUNT tab renders the role-appropriate kill UI:
             FramerUI for the Framer, WolfVoteUI for all other wolf roles.
             This ensures Framer also has access to the Radar (backend allows it — team=="werewolf"). */
          <>
            {wolfTeammates.length > 0 && (
              <div className="night-shell__pack">
                {wolfTeammates.map(p => (
                  <div key={p.player_id} className="night-shell__pack-chip">
                    <span className="night-shell__pack-name">{p.display_name}</span>
                    <span className="night-shell__pack-role">{p.role?.replace(/_/g, ' ')}</span>
                  </div>
                ))}
              </div>
            )}
            <div className="night-shell__tabs">
              <button
                className={`night-shell__tab${wolfTab === 'vote' ? ' night-shell__tab--active' : ''}`}
                onClick={() => setWolfTab('vote')}
              >
                HUNT
              </button>
              <button
                className={`night-shell__tab${wolfTab === 'radar' ? ' night-shell__tab--active' : ''}`}
                onClick={() => setWolfTab('radar')}
              >
                RADAR<Tooltip text={TOOLTIP_RADAR_OVERVIEW} position="below" />
              </button>
            </div>
            {wolfTab === 'vote' ? (
              role === 'framer'
                ? <FramerUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />
                : <WolfVoteUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />
            ) : (
              <WolfRadarUI
                nightActions={nightActions}
                sendIntent={sendIntent}
                latestRipple={latestRipple}
              />
            )}
          </>
        ) : role === 'doctor' ? (
          <DoctorProtectUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />
        ) : role === 'serial_killer' ? (
          <SerialKillerUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />
        ) : role === 'cupid' && gameState.round === 1 ? (
          <CupidUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />
        ) : role === 'arsonist' ? (
          <ArsonistUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />
        ) : role === 'witch' ? (
          <WitchUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />
        ) : role === 'lunatic' ? (
          <LunaticUI myPlayer={myPlayer} sendIntent={sendIntent} />
        ) : role === 'bodyguard' ? (
          <BodyguardUI gameState={gameState} myPlayer={myPlayer} sendIntent={sendIntent} />
        ) : (
          /* Default: wakeOrder==0 villager roles (Villager, Jester, Mayor, Ghost, etc.) */
          <>
            <div className="night-shell__tabs">
              <button
                className={`night-shell__tab${villagerTab === 'archive' ? ' night-shell__tab--active' : ''}`}
                onClick={() => setVillagerTab('archive')}
              >
                ARCHIVE
                {latestArchiveHint && villagerTab !== 'archive' && (
                  <span className="night-shell__tab-dot" />
                )}
              </button>
              <button
                className={`night-shell__tab${villagerTab === 'grid' ? ' night-shell__tab--active' : ''}`}
                onClick={() => setVillagerTab('grid')}
              >
                GRID
                {latestGridHint && villagerTab !== 'grid' && (
                  <span className="night-shell__tab-dot" />
                )}
                <Tooltip text={TOOLTIP_GRID_OVERVIEW} position="below" />
              </button>
            </div>
            {villagerTab === 'archive' ? (
              <VillagerDecoyUI
                myPlayer={myPlayer}
                sendIntent={sendIntent}
                latestHint={latestArchiveHint}
              />
            ) : (
              <GridMapUI
                myPlayer={myPlayer}
                gridLayout={nightActions.grid_layout}
                gridActivity={nightActions.grid_activity}
                sendIntent={sendIntent}
                latestHint={latestGridHint}
              />
            )}
          </>
        )}
      </div>
    </div>
  )
}
