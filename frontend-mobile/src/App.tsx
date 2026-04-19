import React, { useState, useCallback, useEffect, useRef } from 'react'
import { useGameState } from './hooks/useGameState'
import { getApiBase } from './utils/backend'
import { useHaptics } from './hooks/useHaptics'
import type { GridRippleMessage, HintPayload, RedirectMessage } from './types/game'
import OnboardingForm from './components/OnboardingForm/OnboardingForm'
import LobbyWaitingScreen from './components/LobbyWaitingScreen/LobbyWaitingScreen'
import RoleRevealScreen from './components/RoleRevealScreen/RoleRevealScreen'
import NightActionShell from './components/NightActionShell/NightActionShell'
import DayDiscussionScreen from './components/DayDiscussionScreen/DayDiscussionScreen'
import DayVoteScreen from './components/DayVoteScreen/DayVoteScreen'
import HunterPendingScreen from './components/HunterPendingScreen/HunterPendingScreen'
import DeadSpectatorScreen from './components/DeadSpectatorScreen/DeadSpectatorScreen'
import GameOverScreen from './components/GameOverScreen/GameOverScreen'
import SoundPanel from './components/SoundPanel/SoundPanel'
import './App.css'

interface Session {
  game_id: string
  player_id: string
  session_token: string
  permanent_id: string
}

const SESSION_KEY = 'ww_session'
const PERMANENT_ID_KEY = 'ww_permanent_id'
const LAST_GAME_KEY = 'ww_last_game'

function loadSession(): Session | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    return raw ? (JSON.parse(raw) as Session) : null
  } catch { return null }
}

function saveSession(s: Session) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(s))
  // Always track the game_id separately so it survives token expiry / clearSession()
  localStorage.setItem(LAST_GAME_KEY, s.game_id)
}

function clearSession() {
  localStorage.removeItem(SESSION_KEY)
  // Intentionally keep LAST_GAME_KEY — used as rejoin code fallback in OnboardingForm
}

function loadPermanentId(): string | null {
  return localStorage.getItem(PERMANENT_ID_KEY)
}

function savePermanentId(id: string) {
  localStorage.setItem(PERMANENT_ID_KEY, id)
}

const urlParams = new URLSearchParams(window.location.search)
const URL_GAME_CODE = urlParams.get('g') ?? ''

export default function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [bootstrapping, setBootstrapping] = useState(true)
  // Per-source hint arrays — cleared at NIGHT entry so they persist through day discussion.
  const [archiveHints, setArchiveHints] = useState<HintPayload[]>([])
  const [gridHints, setGridHints] = useState<HintPayload[]>([])
  const [latestRipple, setLatestRipple] = useState<GridRippleMessage | null>(null)
  const { vibrate } = useHaptics()

  const handleHint = useCallback((hint: HintPayload) => {
    if (hint.source === 'archive') {
      setArchiveHints(prev => [...prev, hint])
    } else {
      setGridHints(prev => [...prev, hint])
    }
  }, [])

  const handleRipple = useCallback((msg: GridRippleMessage) => {
    setLatestRipple(msg)
  }, [])

  const handleRedirect = useCallback((msg: RedirectMessage) => {
    if (!msg.new_game_id) {
      clearSession()
      setSession(null)
      return
    }
    // Track the new game_id even before the session updates so a player who
    // loses their token before the redirect completes can still rejoin via Join.
    localStorage.setItem(LAST_GAME_KEY, msg.new_game_id)
    setSession(prev => {
      if (!prev) return null
      const entry = msg.players[prev.player_id]
      if (!entry) { clearSession(); return null }
      const newSession: Session = {
        game_id: msg.new_game_id!,
        player_id: entry.new_player_id,
        session_token: entry.new_session_token,
        permanent_id: prev.permanent_id,
      }
      saveSession(newSession)
      return newSession
    })
  }, [])

  // Attempt session rejoin on mount
  useEffect(() => {
    const stored = loadSession()
    if (!stored) { setBootstrapping(false); return }

    fetch(`${getApiBase()}/api/games/${stored.game_id}/rejoin`, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain' },
      body: JSON.stringify({ session_token: stored.session_token }),
    })
      .then(r => {
        if (r.ok) {
          setSession(stored)
        } else if (r.status === 401 || r.status === 404) {
          // Definitively invalid token or game gone — safe to discard
          clearSession()
        } else {
          // 5xx or unexpected status: proceed optimistically.
          // The WS auth handshake is the final arbiter — if the token is
          // actually invalid the WS will close and the player will be prompted.
          setSession(stored)
        }
      })
      .catch(() => {
        // Network error: proceed optimistically, same reasoning as 5xx above.
        setSession(stored)
      })
      .finally(() => setBootstrapping(false))
  }, [])

  const { gameState, roster, sendIntent, status } = useGameState({
    gameId: session?.game_id ?? null,
    playerId: session?.player_id ?? '',
    sessionToken: session?.session_token,
    onHint: handleHint,
    onRedirect: handleRedirect,
    onRipple: handleRipple,
  })

  // Toggle html.phase-lobby for background gradient
  useEffect(() => {
    const isLobby = gameState?.phase === 'lobby'
    document.documentElement.classList.toggle('phase-lobby', isLobby)
    return () => document.documentElement.classList.remove('phase-lobby')
  }, [gameState?.phase])

  // Clear accumulated hints when a NEW night begins (not when night ends).
  // This keeps hints visible through the entire day discussion phase.
  useEffect(() => {
    if (gameState?.phase === 'night') {
      setArchiveHints([])
      setGridHints([])
    }
  }, [gameState?.phase])

  // Detect death transition for long haptic pulse (PRD-002 §3.6)
  const prevAliveRef = useRef<boolean | null>(null)
  useEffect(() => {
    if (!gameState || !session) return
    const myPlayer = gameState.players[session.player_id]
    if (!myPlayer) return
    if (prevAliveRef.current === true && !myPlayer.is_alive) {
      vibrate(500)
    }
    prevAliveRef.current = myPlayer.is_alive
  }, [gameState?.players[session?.player_id ?? '']?.is_alive]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleJoined(s: Session) {
    savePermanentId(s.permanent_id)
    saveSession(s)
    setSession(s)
  }

  // Leave lobby — keep session in localStorage so player can rejoin if accidental
  function handleLeave() {
    setSession(null)
  }

  // Leave match from any phase — fully clears session so OnboardingForm appears clean
  function handleLeaveMatch() {
    clearSession()
    setSession(null)
  }

  // Game over "New Game" — fully clears so no stale rejoin card appears
  function handleNewGame() {
    clearSession()
    setSession(null)
  }

  if (bootstrapping) {
    return <div className="app-loading">Loading…</div>
  }

  // ── No session → Onboarding ──────────────────────────────────────────────────
  if (!session) {
    const storedSession = loadSession()
    // Fall back to the last known game code so a returning player (token expired
    // or missed a rematch redirect) gets the code pre-filled and can re-enter via
    // the join endpoint, which re-issues a token for existing players in any phase.
    const fallbackCode = URL_GAME_CODE || localStorage.getItem(LAST_GAME_KEY) || ''
    return (
      <OnboardingForm
        prefillCode={fallbackCode}
        permanentId={loadPermanentId()}
        onJoined={handleJoined}
        savedSession={storedSession}
        onRejoin={storedSession ? () => setSession(storedSession) : undefined}
      />
    )
  }

  // ── Connecting ───────────────────────────────────────────────────────────────
  if (!gameState) {
    return (
      <>
        <button className="app-leave-btn" onClick={handleLeaveMatch}>Leave</button>
        <div className="app-status">
          <p>
            {status === 'ssl_error'
              ? 'SSL configuration error — contact host'
              : status === 'closed'
                ? 'Reconnecting…'
                : 'Connecting…'}
          </p>
        </div>
      </>
    )
  }

  const myPlayer = gameState.players[session.player_id]
  const { phase } = gameState

  // ── Resolve phase content ──────────────────────────────────────────────────────
  let phaseContent: React.ReactNode = null

  if (phase === 'game_over') {
    phaseContent = (
      <GameOverScreen
        gameState={gameState}
        myPlayerId={session.player_id}
        onLeave={handleNewGame}
      />
    )
  } else if (phase === 'hunter_pending') {
    if (myPlayer && !myPlayer.is_alive && myPlayer.role === 'hunter') {
      phaseContent = (
        <HunterPendingScreen
          gameState={gameState}
          myPlayer={myPlayer}
          sendIntent={sendIntent}
        />
      )
    } else {
      phaseContent = <div className="app-status"><p>Waiting…</p></div>
    }
  } else if (myPlayer && !myPlayer.is_alive) {
    // ── Player eliminated → Dead spectator view (overrides all live phases) ──────
    phaseContent = <DeadSpectatorScreen gameState={gameState} myPlayerId={session.player_id} />
  } else if (phase === 'lobby') {
    phaseContent = (
      <LobbyWaitingScreen
        gameState={gameState}
        roster={roster}
        myPlayerId={session.player_id}
        sendIntent={sendIntent}
        onLeave={handleLeave}
      />
    )
  } else if (phase === 'role_deal') {
    phaseContent = (
      <RoleRevealScreen
        myPlayer={myPlayer!}
        gameState={gameState}
        sendIntent={sendIntent}
      />
    )
  } else if (phase === 'night') {
    phaseContent = (
      <NightActionShell
        gameState={gameState}
        myPlayer={myPlayer!}
        sendIntent={sendIntent}
        latestArchiveHint={archiveHints.length > 0 ? archiveHints[archiveHints.length - 1] : null}
        latestGridHint={gridHints.length > 0 ? gridHints[gridHints.length - 1] : null}
        latestRipple={latestRipple}
      />
    )
  } else if (phase === 'day') {
    phaseContent = (
      <DayDiscussionScreen
        gameState={gameState}
        myPlayerId={session.player_id}
        nightHints={[...archiveHints, ...gridHints]}
      />
    )
  } else if (phase === 'day_vote') {
    phaseContent = (
      <DayVoteScreen
        gameState={gameState}
        myPlayer={myPlayer!}
        sendIntent={sendIntent}
      />
    )
  }

  // Sound panel shown in all phases once the game has started (post-lobby).
  // Even dead spectators and waiting players can trigger sounds.
  const showSoundPanel = phase !== 'lobby'

  return (
    <>
      <button className="app-leave-btn" onClick={handleLeaveMatch}>Leave</button>
      <PlayerInfoBadge
        gameId={session.game_id}
        playerId={session.player_id}
        sessionToken={session.session_token}
        displayName={myPlayer?.display_name ?? '—'}
        role={myPlayer?.role ?? null}
      />
      {phaseContent}
      {showSoundPanel && (
        <SoundPanel
          sendIntent={sendIntent}
          playerName={myPlayer?.display_name ?? ''}
        />
      )}
    </>
  )
}

// ── Player info badge — tap ⓘ to expand/collapse ──────────────────────────────
interface InfoBadgeProps {
  gameId: string
  playerId: string
  sessionToken: string
  displayName: string
  role: string | null
}

function PlayerInfoBadge({ gameId, playerId, sessionToken, displayName, role }: InfoBadgeProps) {
  const [open, setOpen] = useState(false)

  return (
    <div className="info-badge">
      <button
        className="info-badge__toggle"
        onClick={() => setOpen(v => !v)}
        aria-label="Player info"
        aria-expanded={open}
      >
        ⓘ
      </button>
      {open && (
        <div className="info-badge__panel">
          <div className="info-badge__row">
            <span className="info-badge__label">Name</span>
            <span className="info-badge__value">{displayName}</span>
          </div>
          <div className="info-badge__row">
            <span className="info-badge__label">Player ID</span>
            <span className="info-badge__value info-badge__mono">{playerId}</span>
          </div>
          <div className="info-badge__row">
            <span className="info-badge__label">Token</span>
            <span className="info-badge__value info-badge__mono info-badge__truncate">{sessionToken}</span>
          </div>
          <div className="info-badge__row">
            <span className="info-badge__label">Role</span>
            <span className="info-badge__value">{role ?? '—'}</span>
          </div>
          <div className="info-badge__row">
            <span className="info-badge__label">Match ID</span>
            <span className="info-badge__value info-badge__mono">{gameId}</span>
          </div>
        </div>
      )}
    </div>
  )
}
