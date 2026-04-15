import React, { useState, useCallback, useEffect, useRef } from 'react'
import { useGameState } from './hooks/useGameState'
import { useHaptics } from './hooks/useHaptics'
import type { HintPayload, RedirectMessage } from './types/game'
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

function loadSession(): Session | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    return raw ? (JSON.parse(raw) as Session) : null
  } catch { return null }
}

function saveSession(s: Session) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(s))
}

function clearSession() {
  localStorage.removeItem(SESSION_KEY)
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
  const [latestHint, setLatestHint] = useState<HintPayload | null>(null)
  const { vibrate } = useHaptics()

  const handleHint = useCallback((hint: HintPayload) => {
    setLatestHint(hint)
  }, [])

  const handleRedirect = useCallback((msg: RedirectMessage) => {
    if (!msg.new_game_id) {
      clearSession()
      setSession(null)
      return
    }
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

    fetch(`/api/games/${stored.game_id}/rejoin`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
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

  const { gameState, sendIntent, status } = useGameState({
    gameId: session?.game_id ?? null,
    playerId: session?.player_id ?? '',
    sessionToken: session?.session_token,
    onHint: handleHint,
    onRedirect: handleRedirect,
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
    savePermanentId(s.permanent_id)
    saveSession(s)
    setSession(s)
  }

  // Leave lobby — keep session in localStorage so player can rejoin if accidental
  function handleLeave() {
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
    return (
      <OnboardingForm
        prefillCode={URL_GAME_CODE}
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
      <div className="app-status">
        <p>{status === 'closed' ? 'Reconnecting…' : 'Connecting…'}</p>
      </div>
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
        latestHint={latestHint}
      />
    )
  } else if (phase === 'day') {
    phaseContent = (
      <DayDiscussionScreen
        gameState={gameState}
        myPlayerId={session.player_id}
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
