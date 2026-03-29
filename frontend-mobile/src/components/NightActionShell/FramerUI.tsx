import { useState } from 'react'
import { useHaptics } from '../../hooks/useHaptics'
import PlayerAvatar from '../PlayerAvatar/PlayerAvatar'
import type { PlayerState, StrippedGameState } from '../../types/game'
import './ActionUI.css'

interface Props {
  gameState: StrippedGameState
  myPlayer: PlayerState
  sendIntent: (payload: Record<string, unknown>) => void
}

type Mode = null | 'frame' | 'hack_archives'

interface Preset {
  id: string
  label: string
  category: string
  text: string
}

const PRESETS: Preset[] = [
  { id: 'wolf_count_one',    label: 'Only 1 Wolf',       category: 'wolf_count',     text: 'There is only 1 Wolf in this game.' },
  { id: 'wolf_count_two',    label: '2 Wolves total',    category: 'wolf_count',     text: 'There are 2 Wolves total in this game.' },
  { id: 'wolf_count_four',   label: '4 Wolves total',    category: 'wolf_count',     text: 'There are 4 Wolves total in this game.' },
  { id: 'no_doctor',         label: 'No Doctor',         category: 'no_role_present',text: 'There is NO Doctor in this game.' },
  { id: 'no_seer',           label: 'No Seer here',      category: 'no_role_present',text: 'There is NO Seer in this game.' },
  { id: 'no_tracker',        label: 'No Tracker',        category: 'no_role_present',text: 'There is NO Tracker in this game.' },
  { id: 'no_alpha',          label: 'No Alpha Wolf',     category: 'no_role_present',text: 'There is NO Alpha Wolf in this game.' },
  { id: 'sk_present',        label: 'SK exists',         category: 'role_present',   text: 'There IS a Serial Killer in this game.' },
  { id: 'alpha_present',     label: 'Alpha Wolf exists', category: 'role_present',   text: 'There IS an Alpha Wolf in this game.' },
  { id: 'infector_present',  label: 'Infector exists',   category: 'role_present',   text: 'There IS an Infector in this game.' },
]

const HACK_ROLES = ['alpha_wolf', 'framer', 'infector', 'doctor', 'tracker', 'serial_killer', 'arsonist']

const CATEGORY_LABELS: Record<string, string> = {
  wolf_count:     'There are {N} Wolves',
  no_role_present:'There is NO {role}',
  role_present:   'There IS a {role}',
}

function buildText(category: string, param: string): string {
  if (category === 'wolf_count') return `There are ${param} Wolves total in this game.`
  if (category === 'no_role_present') return `There is NO ${param.replace(/_/g, ' ')} in this game.`
  if (category === 'role_present') return `There IS a ${param.replace(/_/g, ' ')} in this game.`
  return ''
}

export default function FramerUI({ gameState, myPlayer, sendIntent }: Props) {
  const [mode, setMode] = useState<Mode>(null)
  const { vibrate } = useHaptics()

  if (mode === null) {
    return <ModeSelect onSelect={setMode} />
  }

  if (mode === 'frame') {
    return (
      <FrameTarget
        gameState={gameState}
        myPlayer={myPlayer}
        sendIntent={sendIntent}
        vibrate={vibrate}
        onBack={() => setMode(null)}
      />
    )
  }

  return (
    <HackArchives
      gameState={gameState}
      myPlayer={myPlayer}
      sendIntent={sendIntent}
      vibrate={vibrate}
      onBack={() => setMode(null)}
    />
  )
}

// ── Step 1: Mode selection ────────────────────────────────────────────────────

function ModeSelect({ onSelect }: { onSelect: (m: 'frame' | 'hack_archives') => void }) {
  return (
    <div className="action-ui action-ui--centered">
      <p className="action-ui__header">What is your move tonight?</p>
      <div className="action-ui__mode-row">
        <button
          className="action-ui__mode-btn action-ui__mode-btn--frame"
          onClick={() => onSelect('frame')}
        >
          Frame a Player
        </button>
        <button
          className="action-ui__mode-btn action-ui__mode-btn--hack"
          onClick={() => onSelect('hack_archives')}
        >
          Hack the Archives
        </button>
      </div>
    </div>
  )
}

// ── Step 2a: Frame a player ───────────────────────────────────────────────────

interface FrameProps {
  gameState: StrippedGameState
  myPlayer: PlayerState
  sendIntent: (payload: Record<string, unknown>) => void
  vibrate: (pattern: number | number[]) => void
  onBack: () => void
}

function FrameTarget({ gameState, myPlayer, sendIntent, vibrate, onBack }: FrameProps) {
  const [frameTarget, setFrameTarget] = useState<string | null>(null)
  const [wolfVote, setWolfVote] = useState<string | null>(null)

  const targets = Object.values(gameState.players).filter(p =>
    p.is_alive && p.player_id !== myPlayer.player_id && p.team !== 'werewolf',
  )

  function handleConfirm() {
    if (!frameTarget) return
    vibrate(300)
    const payload: Record<string, unknown> = {
      type: 'submit_night_action',
      framer_action: 'frame',
      target_id: frameTarget,
    }
    if (wolfVote) payload.wolf_vote_target_id = wolfVote
    sendIntent(payload)
  }

  return (
    <div className="action-ui">
      <button className="action-ui__back" onClick={onBack}>← Back</button>
      <p className="action-ui__header">Choose a player to frame</p>

      <div className="action-ui__list">
        {targets.map(p => (
          <button
            key={p.player_id}
            className={`action-ui__row ${frameTarget === p.player_id ? 'action-ui__row--selected action-ui__row--wolf' : ''}`}
            onClick={() => setFrameTarget(p.player_id)}
          >
            <PlayerAvatar player={p} />
            <span>{p.display_name}</span>
          </button>
        ))}
      </div>

      <p className="action-ui__sub-header">Wolf vote (optional)</p>
      <div className="action-ui__list">
        {targets.map(p => (
          <button
            key={p.player_id}
            className={`action-ui__row ${wolfVote === p.player_id ? 'action-ui__row--selected action-ui__row--wolf' : ''}`}
            onClick={() => setWolfVote(prev => prev === p.player_id ? null : p.player_id)}
          >
            <PlayerAvatar player={p} />
            <span>{p.display_name}</span>
          </button>
        ))}
      </div>

      <button
        className="action-ui__confirm"
        disabled={!frameTarget}
        onClick={handleConfirm}
      >
        Frame
      </button>
    </div>
  )
}

// ── Step 2b: Hack the Archives ────────────────────────────────────────────────

interface HackProps {
  gameState: StrippedGameState
  myPlayer: PlayerState
  sendIntent: (payload: Record<string, unknown>) => void
  vibrate: (pattern: number | number[]) => void
  onBack: () => void
}

function HackArchives({ gameState, myPlayer, sendIntent, vibrate, onBack }: HackProps) {
  const [category, setCategory] = useState('')
  const [param, setParam] = useState('')
  const [wolfVote, setWolfVote] = useState<string | null>(null)
  const [submitted, setSubmitted] = useState(false)

  const targets = Object.values(gameState.players).filter(p =>
    p.is_alive && p.player_id !== myPlayer.player_id && p.team !== 'werewolf',
  )

  const preview = category && param ? buildText(category, param) : ''
  const canSubmit = Boolean(category && param)

  function applyPreset(preset: Preset) {
    setCategory(preset.category)
    if (preset.category === 'wolf_count') {
      const match = preset.text.match(/\d+/)
      setParam(match ? match[0] : '')
    } else {
      // Extract role name from text
      const roleMatch = preset.text.match(/NO (.+) in|IS a (.+) in/)
      const roleName = roleMatch ? (roleMatch[1] ?? roleMatch[2] ?? '') : ''
      setParam(roleName.toLowerCase().replace(/ /g, '_'))
    }
  }

  function handleSubmit() {
    if (!canSubmit) return
    vibrate(300)
    const payload: Record<string, unknown> = {
      type: 'submit_night_action',
      framer_action: 'hack_archives',
      false_hint_category: category,
      false_hint_text: preview,
    }
    if (wolfVote) payload.wolf_vote_target_id = wolfVote
    sendIntent(payload)
    setSubmitted(true)
  }

  if (submitted) {
    return (
      <div className="action-ui action-ui--centered">
        <p className="action-ui__hint-pending" style={{ color: 'var(--timer-warning, #f6ad55)' }}>
          False clue injected. Let the chaos begin.
        </p>
      </div>
    )
  }

  return (
    <div className="action-ui">
      <button className="action-ui__back" onClick={onBack}>← Back</button>
      <p className="action-ui__header">Craft your false clue</p>

      <p className="action-ui__sub-header">Quick Pick</p>
      <div className="action-ui__chip-row">
        {PRESETS.map(preset => (
          <button
            key={preset.id}
            className={`action-ui__chip ${category === preset.category && preview === buildText(preset.category, param) && preset.text === preview ? 'action-ui__chip--selected' : ''}`}
            onClick={() => applyPreset(preset)}
          >
            {preset.label}
          </button>
        ))}
      </div>

      <p className="action-ui__sub-header">— or build your own —</p>

      <div className="action-ui__field-row">
        <label className="action-ui__label">Category</label>
        <select
          className="action-ui__select"
          value={category}
          onChange={e => { setCategory(e.target.value); setParam('') }}
        >
          <option value="">Select…</option>
          {Object.entries(CATEGORY_LABELS).map(([val, label]) => (
            <option key={val} value={val}>{label}</option>
          ))}
        </select>
      </div>

      {category === 'wolf_count' && (
        <div className="action-ui__field-row">
          <label className="action-ui__label">Wolf count</label>
          <select
            className="action-ui__select"
            value={param}
            onChange={e => setParam(e.target.value)}
          >
            <option value="">Select…</option>
            {['1','2','3','4','5','6'].map(n => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </div>
      )}

      {(category === 'no_role_present' || category === 'role_present') && (
        <div className="action-ui__field-row">
          <label className="action-ui__label">Role</label>
          <select
            className="action-ui__select"
            value={param}
            onChange={e => setParam(e.target.value)}
          >
            <option value="">Select…</option>
            {HACK_ROLES.map(r => (
              <option key={r} value={r}>{r.replace(/_/g, ' ')}</option>
            ))}
          </select>
        </div>
      )}

      {preview && (
        <p className="action-ui__hint-preview">{preview}</p>
      )}

      <p className="action-ui__sub-header">Wolf vote (optional)</p>
      <div className="action-ui__list">
        {targets.map(p => (
          <button
            key={p.player_id}
            className={`action-ui__row ${wolfVote === p.player_id ? 'action-ui__row--selected action-ui__row--wolf' : ''}`}
            onClick={() => setWolfVote(prev => prev === p.player_id ? null : p.player_id)}
          >
            <PlayerAvatar player={p} />
            <span>{p.display_name}</span>
          </button>
        ))}
      </div>

      <button
        className="action-ui__confirm action-ui__confirm--hack"
        disabled={!canSubmit}
        onClick={handleSubmit}
      >
        Inject Hint
      </button>
    </div>
  )
}
