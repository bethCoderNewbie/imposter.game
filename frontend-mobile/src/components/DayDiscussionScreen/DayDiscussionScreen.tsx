import { useState, useEffect } from 'react'
import { useTimer } from '../../hooks/useTimer'
import PlayerAvatar from '../PlayerAvatar/PlayerAvatar'
import type { StrippedGameState } from '../../types/game'
import './DayDiscussionScreen.css'

type NoteTag = 'Sus' | 'Safe' | '?'

interface Props {
  gameState: StrippedGameState
  myPlayerId: string
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

export default function DayDiscussionScreen({ gameState, myPlayerId }: Props) {
  const { secondsRemaining, isWarning, isCritical } = useTimer(gameState.timer_ends_at)
  const [notepadOpen, setNotepadOpen] = useState(false)
  const [tags, setTags] = useState<Record<string, NoteTag>>({})

  const players = Object.values(gameState.players).filter(p => p.player_id !== myPlayerId)

  useEffect(() => {
    pruneStaleNotes(gameState.game_id)
    // Load existing tags
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
  const timerClass = isCritical ? 'timer--critical' : isWarning ? 'timer--warning' : ''

  return (
    <div className="day-discussion">
      {/* Header */}
      <div className="day-discussion__header">
        <span className="day-discussion__round">Day {gameState.round}</span>
        <span className={`day-discussion__timer ${timerClass}`}>{mm}:{ss}</span>
      </div>

      {/* Phase label */}
      <p className="day-discussion__phase">Discussion — Speak up!</p>

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
