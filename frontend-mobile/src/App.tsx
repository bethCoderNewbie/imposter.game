import { useState, useCallback, useEffect, useRef } from 'react'
import { useGameState } from './hooks/useGameState'
import { useHaptics } from './hooks/useHaptics'
import type { HintPayload } from './types/game'
import OnboardingForm from './components/OnboardingForm/OnboardingForm'
import LobbyWaitingScreen from './components/LobbyWaitingScreen/LobbyWaitingScreen'
import RoleRevealScreen from './components/RoleRevealScreen/RoleRevealScreen'
import NightActionShell from './components/NightActionShell/NightActionShell'
import DayDiscussionScreen from './components/DayDiscussionScreen/DayDiscussionScreen'
import DayVoteScreen from './components/DayVoteScreen/DayVoteScreen'
import DeadSpectatorScreen from './components/DeadSpectatorScreen/DeadSpectatorScreen'
import './App.css'

interface Session {
  game_id: string
  player_id: string
  session_token: string
}

const SESSION_KEY = 'ww_session'

function loadSession(): Session | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY)
    return raw ? (JSON.parse(raw) as Session) : null
  } catch { return null }
}

function saveSession(s: Session) {
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(s))
}

function clearSession() {
  sessionStorage.removeItem(SESSION_KEY)
}

const urlParams = new URLSearchParams(window.location.search)
const URL_GAME_CODE = urlParams.get('g') ?? ''

export default function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [bootstrapping, setBootstrapping] = useState(true)
  const [latestHint, setLatestHint] = useState<HintPayload | null>(null)
  const { vibrate } = useHaptics()

  const handleHint = useCallback((hint: HintPayload) => {
    setLatestHint(hint)
  }, [])

  // Attempt session rejoin on mount
  useEffect(() => {
    const stored = loadSession()
    if (!stored) { setBootstrapping(false); return }

    fetch(`/api/games/${stored.game_id}/rejoin`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_token: stored.session_token }),
    })
      .then(r => {
        if (r.ok) {
          setSession(stored)
        } else {
          clearSession()
        }
      })
      .catch(() => clearSession())
      .finally(() => setBootstrapping(false))
  }, [])

  const { gameState, sendIntent, status } = useGameState({
    gameId: session?.game_id ?? null,
    playerId: session?.player_id ?? '',
    sessionToken: session?.session_token,
    onHint: handleHint,
  })

  // Clear hint when night phase ends
  useEffect(() => {
    if (gameState?.phase !== 'night') setLatestHint(null)
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
    saveSession(s)
    setSession(s)
  }

  if (bootstrapping) {
    return <div className="app-loading">Loading…</div>
  }

  // ── No session → Onboarding ──────────────────────────────────────────────────
  if (!session) {
    return <OnboardingForm prefillCode={URL_GAME_CODE} onJoined={handleJoined} />
  }

  // ── Connecting ───────────────────────────────────────────────────────────────
  if (!gameState) {
    return (
      <div className="app-status">
        <p>{status === 'connecting' ? 'Connecting…' : 'Reconnecting…'}</p>
      </div>
    )
  }

  const myPlayer = gameState.players[session.player_id]

  // ── Player eliminated → Dead spectator view (overrides all phases) ───────────
  if (myPlayer && !myPlayer.is_alive) {
    return <DeadSpectatorScreen gameState={gameState} myPlayerId={session.player_id} />
  }

  const { phase } = gameState

  if (phase === 'lobby') {
    return (
      <LobbyWaitingScreen
        gameState={gameState}
        myPlayerId={session.player_id}
        sendIntent={sendIntent}
      />
    )
  }

  if (phase === 'role_deal') {
    return (
      <RoleRevealScreen
        myPlayer={myPlayer!}
        gameState={gameState}
        sendIntent={sendIntent}
      />
    )
  }

  if (phase === 'night') {
    return (
      <NightActionShell
        gameState={gameState}
        myPlayer={myPlayer!}
        sendIntent={sendIntent}
        latestHint={latestHint}
      />
    )
  }

  if (phase === 'day') {
    return (
      <DayDiscussionScreen
        gameState={gameState}
        myPlayerId={session.player_id}
      />
    )
  }

  if (phase === 'day_vote' || phase === 'hunter_pending') {
    return (
      <DayVoteScreen
        gameState={gameState}
        myPlayer={myPlayer!}
        sendIntent={sendIntent}
      />
    )
  }

  if (phase === 'game_over') {
    return (
      <div className="game-over-mobile">
        <h1>{gameState.winner === 'village' ? 'Village Wins!' : 'Wolves Win!'}</h1>
        {myPlayer?.role && <p>Your role: <strong>{myPlayer.role}</strong></p>}
        <button onClick={() => { clearSession(); setSession(null) }}>
          Play Again
        </button>
      </div>
    )
  }

  return null
}
