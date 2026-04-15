import { useState, useEffect, useRef, useCallback } from 'react'
import { useGameState } from './hooks/useGameState'
import { useNarrator } from './hooks/useNarrator'
import CreateMatchScreen from './components/CreateMatchScreen/CreateMatchScreen'
import LobbyScreen from './components/LobbyScreen/LobbyScreen'
import NightScreen from './components/NightScreen/NightScreen'
import NightResolution from './components/NightResolution/NightResolution'
import DayScreen from './components/DayScreen/DayScreen'
import GameOverScreen from './components/GameOverScreen/GameOverScreen'
import NarratorSubtitle from './components/NarratorSubtitle/NarratorSubtitle'
import type { StrippedGameState } from './types/game'
import './App.css'

// PRD-003 §4 — substrate class swap on root element (never via component JSX)
const PHASE_TO_CLASS: Record<string, string> = {
  lobby:           'phase-lobby',
  role_deal:       'phase-lobby',
  night:           'phase-night',
  day:             'phase-day',
  day_vote:        'phase-day',
  hunter_pending:  'phase-day',
  game_over:       'phase-day',
}

export default function App() {
  const [audioUnlocked, setAudioUnlocked] = useState(false)
  const [gameId, setGameId] = useState<string | null>(() => {
    const p = new URLSearchParams(window.location.search)
    return p.get('g')
  })
  const [hostSecret, setHostSecret] = useState<string | null>(() => {
    const p = new URLSearchParams(window.location.search)
    const gId = p.get('g')
    if (!gId) return null
    return p.get('host_secret') ?? localStorage.getItem(`ww_host_${gId}`)
  })
  // Show NightResolution interstitial on night→day transition
  const [showResolution, setShowResolution] = useState(false)
  // Snapshot of game state at resolution moment (so component has stable data)
  const [resolutionState, setResolutionState] = useState<StrippedGameState | null>(null)
  // Freeze votes at the moment day_vote closes (for VoteWeb reveal-all-at-once)
  const [frozenVotes, setFrozenVotes] = useState<Record<string, string> | null>(null)
  const prevPhaseRef = useRef<string | null>(null)
  // Pending scream timeout — cancelled if night ends before it fires (PRD-012 §2.3)
  const screamTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Brief toast shown when a player triggers a sound from the mobile sound board
  const [soundToast, setSoundToast] = useState<{ emoji: string; playerName: string } | null>(null)
  const soundToastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { narratorText, handleNarrate } = useNarrator()

  // Handle a fun sound triggered by a player on mobile
  const SOUND_EMOJIS: Record<string, string> = {
    howl: '🐺', wolfcry: '🌕', spooky: '👻', boom: '💥',
    siren: '🚨', ambulance: '🚑', warning: '⚠️', surprise: '🎉',
    gasp: '😱', laugh: '😂', clap: '👏', people: '👥',
    fail: '🎺', burp: '🤢', fart: '💨', walk: '🚶',
    snoring: '😴', shush: '🤫', flashback: '⏪',
  }
  const handleSoundTriggered = useCallback((soundId: string, playerName: string) => {
    if (!audioUnlocked) return
    const audio = new Audio(`${import.meta.env.BASE_URL}audio/sounds/${soundId}.mp3`)
    audio.volume = 0.75
    audio.play().catch(() => {})
    // Show toast for 2.5s
    if (soundToastTimerRef.current) clearTimeout(soundToastTimerRef.current)
    setSoundToast({ emoji: SOUND_EMOJIS[soundId] ?? '🔊', playerName })
    soundToastTimerRef.current = setTimeout(() => setSoundToast(null), 2500)
  }, [audioUnlocked]) // eslint-disable-line react-hooks/exhaustive-deps

  // Schedule a scream SFX with a random 3–30s delay after the first wolf kill vote
  const handleWolfKillQueued = useCallback(() => {
    if (!audioUnlocked) return
    const delay = Math.random() * (30000 - 3000) + 3000
    screamTimeoutRef.current = setTimeout(() => {
      const audio = new Audio(`${import.meta.env.BASE_URL}audio/scream.mp3`)
      audio.volume = 0.7
      audio.play().catch(() => {})
    }, delay)
  }, [audioUnlocked])

  // Sync hostSecret from URL (or localStorage fallback) whenever gameId changes
  useEffect(() => {
    const p = new URLSearchParams(window.location.search)
    const gId = p.get('g')
    if (!gId) { setHostSecret(null); return }
    setHostSecret(p.get('host_secret') ?? localStorage.getItem(`ww_host_${gId}`))
  }, [gameId])

  // Reset per-game display state when switching to a new game (rematch).
  // Without this, frozenVotes from the ended game bleeds into the new game's
  // DayScreen (wrong vote arrows), and a mid-animation NightResolution stays
  // visible instead of the new game's lobby.
  useEffect(() => {
    setFrozenVotes(null)
    setShowResolution(false)
    setResolutionState(null)
    prevPhaseRef.current = null
  }, [gameId])

  function handleCreated(newGameId: string, newHostSecret: string) {
    localStorage.setItem(`ww_host_${newGameId}`, newHostSecret)
    history.pushState({}, '', `?g=${newGameId}&host_secret=${newHostSecret}`)
    setGameId(newGameId)
    setHostSecret(newHostSecret)
  }

  function handleResumed(resumeGameId: string) {
    history.pushState({}, '', `?g=${resumeGameId}`)
    setGameId(resumeGameId)
    // hostSecret stays null — resumed/spectator flow
  }

  const { gameState, status } = useGameState({
    gameId,
    playerId: 'display',
    onNarrate: handleNarrate,
    onWolfKillQueued: handleWolfKillQueued,
    onSoundTriggered: handleSoundTriggered,
  })

  // PRD-003 §4 rule: substrate class set here, not inside components
  useEffect(() => {
    if (!gameState) return
    const cls = PHASE_TO_CLASS[gameState.phase] ?? ''
    document.documentElement.className = cls
  }, [gameState?.phase])

  // Detect phase transitions
  useEffect(() => {
    if (!gameState) return
    const prev = prevPhaseRef.current
    const curr = gameState.phase

    if (prev === 'night' && (curr === 'day' || curr === 'day_vote')) {
      setResolutionState(gameState)
      setShowResolution(true)
      document.documentElement.className = 'phase-night-resolution'
      // Cancel any pending scream that hasn't fired yet (PRD-012 §2.3)
      if (screamTimeoutRef.current) {
        clearTimeout(screamTimeoutRef.current)
        screamTimeoutRef.current = null
      }
    }

    // Freeze day_vote votes for VoteWeb reveal when voting closes
    if (prev === 'day_vote' && curr !== 'day_vote') {
      setFrozenVotes({ ...gameState.day_votes })
    }

    prevPhaseRef.current = curr
  }, [gameState?.phase]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleClickToBegin() {
    document.documentElement.requestFullscreen?.().catch(() => {})
    setAudioUnlocked(true)
  }

  // Extract render logic into a helper so NarratorSubtitle can be mounted alongside
  function renderContent() {
    // ── "Click to Begin" overlay (audio unlock + fullscreen entry) ──────────────
    if (!audioUnlocked) {
      return (
        <div className="click-to-begin" onClick={handleClickToBegin}>
          <div className="click-to-begin__content">
            <span className="click-to-begin__icon">▶</span>
            <p>Click to begin</p>
          </div>
        </div>
      )
    }

    // ── No game ID → Create match screen ────────────────────────────────────────
    if (!gameId) {
      return <CreateMatchScreen onCreated={handleCreated} onResumed={handleResumed} />
    }

    // ── Night Resolution interstitial (4 s, non-skippable) ──────────────────────
    if (showResolution && resolutionState) {
      return (
        <NightResolution
          gameState={resolutionState}
          onComplete={() => {
            setShowResolution(false)
            setResolutionState(null)
            if (gameState) {
              document.documentElement.className = PHASE_TO_CLASS[gameState.phase] ?? ''
            }
          }}
        />
      )
    }

    // ── Waiting for connection / first state broadcast ───────────────────────────
    if (!gameState) {
      return (
        <div className="status-screen">
          <p>{status === 'connecting' ? 'Connecting…' : 'Waiting for game…'}</p>
        </div>
      )
    }

    const { phase } = gameState

    if (phase === 'lobby' || phase === 'role_deal') {
      return (
        <LobbyScreen
          gameState={gameState}
          hostSecret={hostSecret ?? undefined}
          gameId={gameId ?? undefined}
        />
      )
    }

    if (phase === 'night') {
      return <NightScreen gameState={gameState} audioUnlocked={audioUnlocked} />
    }

    if (phase === 'day' || phase === 'day_vote' || phase === 'hunter_pending') {
      return <DayScreen gameState={gameState} frozenVotes={frozenVotes} audioUnlocked={audioUnlocked} />
    }

    if (phase === 'game_over') {
      return (
        <GameOverScreen
          gameState={gameState}
          audioUnlocked={audioUnlocked}
          gameId={gameId}
          hostSecret={hostSecret}
          onPlayAgain={(newGameId, newHostSecret) => {
            localStorage.setItem(`ww_host_${newGameId}`, newHostSecret)
            history.pushState({}, '', `?g=${newGameId}&host_secret=${newHostSecret}`)
            setGameId(newGameId)
            setHostSecret(newHostSecret)
          }}
          onNewMatch={() => {
            history.pushState({}, '', import.meta.env.BASE_URL)
            setGameId(null)
            setHostSecret(null)
          }}
        />
      )
    }

    return null
  }

  return (
    <>
      {renderContent()}
      {audioUnlocked && <NarratorSubtitle text={narratorText} />}
      {soundToast && (
        <div className="sound-toast">
          <span className="sound-toast__emoji">{soundToast.emoji}</span>
          <span className="sound-toast__name">{soundToast.playerName}</span>
        </div>
      )}
    </>
  )
}
