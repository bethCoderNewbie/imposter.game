import { useState, useEffect } from 'react'
import { useTimer } from '../../hooks/useTimer'
import PlayerAvatar from '../PlayerAvatar/PlayerAvatar'
import type {
  HintPayload,
  InvestigationResult,
  SonarPingResult,
  StrippedGameState,
} from '../../types/game'
import './DayDiscussionScreen.css'

type NoteTag = 'Sus' | 'Safe' | '?'

interface Props {
  gameState: StrippedGameState
  myPlayerId: string
  nightHints?: HintPayload[]
}

function noteKey(gameId: string, myId: string, targetId: string) {
  return `ww_note_${gameId}_${myId}_${targetId}`
}

/** ADR-003 §7 — localStorage notepad with room-scoped keys.
 *  Prune stale keys from other games on mount. */
function pruneStaleNotes(currentGameId: string) {
  const toRemove: string[] = []
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i)
    if (k?.startsWith('ww_note_') && !k.includes(`ww_note_${currentGameId}_`)) {
      toRemove.push(k)
    }
  }
  toRemove.forEach(k => localStorage.removeItem(k))
}

export default function DayDiscussionScreen({ gameState, myPlayerId, nightHints = [] }: Props) {
  const paused = gameState.timer_paused ?? false
  const { secondsRemaining: liveSeconds, isWarning, isCritical } = useTimer(gameState.timer_ends_at)
  const secondsRemaining = paused ? (gameState.timer_remaining_seconds ?? 0) : liveSeconds
  const [notepadOpen, setNotepadOpen] = useState(false)
  const [tags, setTags] = useState<Record<string, NoteTag>>({})

  const myPlayer = gameState.players[myPlayerId]
  const isSeer   = myPlayer?.role === 'seer'
  const isWolf   = myPlayer?.team === 'werewolf'

  const players = Object.values(gameState.players).filter(p => p.player_id !== myPlayerId)

  useEffect(() => {
    pruneStaleNotes(gameState.game_id)
    const loaded: Record<string, NoteTag> = {}
    players.forEach(p => {
      const val = localStorage.getItem(noteKey(gameState.game_id, myPlayerId, p.player_id))
      if (val) loaded[p.player_id] = val as NoteTag
    })
    setTags(loaded)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  function cycleTag(playerId: string) {
    setTags(prev => {
      const current = prev[playerId] ?? '?'
      const next: NoteTag = current === '?' ? 'Sus' : current === 'Sus' ? 'Safe' : '?'
      const key = noteKey(gameState.game_id, myPlayerId, playerId)
      if (next === '?') {
        localStorage.removeItem(key)
      } else {
        localStorage.setItem(key, next)
      }
      return { ...prev, [playerId]: next }
    })
  }

  const mm = String(Math.floor(secondsRemaining / 60)).padStart(2, '0')
  const ss = String(secondsRemaining % 60).padStart(2, '0')
  const timerClass = paused ? 'timer--paused' : isCritical ? 'timer--critical' : isWarning ? 'timer--warning' : ''

  return (
    <div className="day-discussion">
      {/* Header */}
      <div className="day-discussion__header">
        <span className="day-discussion__round">Day {gameState.round}</span>
        <span className={`day-discussion__timer ${timerClass}`}>
          {paused && <span className="day-discussion__paused">PAUSED </span>}
          {mm}:{ss}
        </span>
      </div>

      {/* Phase label */}
      <p className="day-discussion__phase">Discussion — Speak up!</p>

      {/* Seer intel — seer role only */}
      {isSeer && <SeerIntelPanel gameState={gameState} />}

      {/* Grid intel — villagers/wakeOrder==0 players who earned hints last night */}
      {!isWolf && nightHints.length > 0 && (
        <GridIntelPanel hints={nightHints} />
      )}

      {/* Radar summary — wolf-team only */}
      {isWolf && <RadarSummaryPanel gameState={gameState} />}

      {/* Private notepad */}
      <div className="day-discussion__notepad">
        <button
          className="day-discussion__notepad-toggle"
          onClick={() => setNotepadOpen(o => !o)}
        >
          📝 Notes {notepadOpen ? '▲' : '▼'}
        </button>

        {notepadOpen && (
          <div className="day-discussion__notepad-content">
            {players.filter(p => p.is_alive).map(p => (
              <div key={p.player_id} className="day-discussion__note-row">
                <PlayerAvatar player={p} size={32} />
                <span className="day-discussion__note-name">{p.display_name}</span>
                <button
                  className={`day-discussion__tag day-discussion__tag--${(tags[p.player_id] ?? '?').toLowerCase().replace('?', 'unknown')}`}
                  onClick={() => cycleTag(p.player_id)}
                >
                  {tags[p.player_id] ?? '?'}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}


// ── Seer Intel Panel ──────────────────────────────────────────────────────────

function SeerIntelPanel({ gameState }: { gameState: StrippedGameState }) {
  const knowledge = gameState.seer_knowledge ?? {}
  const entries = Object.entries(knowledge) as [string, InvestigationResult][]

  if (entries.length === 0 && !gameState.night_actions.seer_result) {
    return null
  }

  return (
    <div className="day-discussion__intel-panel">
      <p className="day-discussion__intel-label">🔮 Your Intel</p>
      <div className="day-discussion__intel-list">
        {entries.map(([targetId, result]) => {
          const name = gameState.players[targetId]?.display_name ?? targetId
          return (
            <p
              key={targetId}
              className={`day-discussion__seer-row day-discussion__seer-row--${result}`}
            >
              {name} — {result === 'wolf' ? 'WOLF' : result === 'neutral' ? 'Neutral' : 'Not Wolf'}
            </p>
          )
        })}
      </div>
    </div>
  )
}


// ── Grid Intel Panel (villagers) ──────────────────────────────────────────────

const HINT_TIER: Record<string, 1 | 2 | 3> = {
  // Tier 1 — composition
  wolf_count: 1, no_role_present: 1, role_present: 1,
  neutral_exists: 1, non_wolf_kill: 1, lovers_exist: 1,
  alive_count: 1, role_alive_check: 1, night_recap: 1,
  // Tier 2 — relational
  one_of_three: 2, same_alignment: 2, diff_alignment: 2, positional_clue: 2,
  // Tier 3 — specific intel
  innocent_clear: 3, action_log: 3,
}

const HINT_TIER_LABEL: Record<1 | 2 | 3, string> = {
  1: 'T1', 2: 'T2', 3: 'T3',
}

function GridIntelPanel({ hints }: { hints: HintPayload[] }) {
  const [open, setOpen] = useState(true)

  return (
    <div className="day-discussion__intel-panel">
      <button
        className="day-discussion__intel-toggle"
        onClick={() => setOpen(o => !o)}
      >
        Your Intel ({hints.length}) {open ? '▲' : '▼'}
      </button>
      {open && (
        <div className="day-discussion__intel-list">
          {hints.map(h => {
            const tier = HINT_TIER[h.category] ?? 1
            return (
              <div key={h.hint_id} className="day-discussion__hint-row">
                <span className="day-discussion__hint-source">
                  {h.source === 'archive' ? '📜' : '🔷'}
                </span>
                <span className={`day-discussion__hint-tier day-discussion__hint-tier--t${tier}`}>
                  {HINT_TIER_LABEL[tier]}
                </span>
                <span className="day-discussion__hint-text">{h.text}</span>
                {h.expires_after_round !== null && (
                  <span className="day-discussion__hint-expiry">
                    expires R{h.expires_after_round}
                  </span>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}


// ── Radar Summary Panel (wolves) ──────────────────────────────────────────────

const TIER_COLORS: Record<string, string> = {
  '1': '#38a169', '2': '#d69e2e', '3': '#e53e3e',
}

function RadarSummaryPanel({ gameState }: { gameState: StrippedGameState }) {
  const [open, setOpen] = useState(true)
  const na = gameState.night_actions
  const pingResults: SonarPingResult[] = na.sonar_ping_results ?? []
  const totalActivity = (na.grid_activity ?? []).length
  const pingsUsed = na.sonar_pings_used ?? 0

  if (pingsUsed === 0 && totalActivity === 0) {
    return null
  }

  return (
    <div className="day-discussion__intel-panel day-discussion__intel-panel--wolf">
      <button
        className="day-discussion__intel-toggle day-discussion__intel-toggle--wolf"
        onClick={() => setOpen(o => !o)}
      >
        📡 Radar Summary {open ? '▲' : '▼'}
      </button>
      {open && (
        <div className="day-discussion__intel-list">
          {/* Overall activity */}
          <p className="day-discussion__radar-stat">
            <span className="day-discussion__radar-stat-label">Nodes solved</span>
            <span className="day-discussion__radar-stat-value">{totalActivity}</span>
          </p>
          <p className="day-discussion__radar-stat">
            <span className="day-discussion__radar-stat-label">Pings used</span>
            <span className="day-discussion__radar-stat-value">{pingsUsed} / 4</span>
          </p>

          {/* Per-quadrant ping results */}
          {pingResults.length > 0 && (
            <div className="day-discussion__ping-results">
              {pingResults.map((r, i) => (
                <div key={i} className="day-discussion__ping-row">
                  <span className="day-discussion__ping-quadrant">
                    {r.quadrant.replace('_', '-')}
                  </span>
                  <span className="day-discussion__ping-heat">{r.heat} node{r.heat !== 1 ? 's' : ''}</span>
                  <span className="day-discussion__ping-tiers">
                    {([1, 2, 3] as const).map(t => {
                      const count = r.tier_counts?.[t] ?? 0
                      return count > 0 ? (
                        <span key={t} style={{ color: TIER_COLORS[t] }}>
                          {count}×T{t}
                        </span>
                      ) : null
                    })}
                    {Object.values(r.tier_counts ?? {}).every(v => v === 0) && (
                      <span className="day-discussion__ping-empty">quiet</span>
                    )}
                  </span>
                </div>
              ))}
            </div>
          )}

          {pingsUsed === 0 && totalActivity > 0 && (
            <p className="day-discussion__radar-note">
              No pings used — {totalActivity} node{totalActivity !== 1 ? 's' : ''} solved across the grid.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
