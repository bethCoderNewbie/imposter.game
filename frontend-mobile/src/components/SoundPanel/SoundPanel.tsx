import { useState, useCallback, useRef } from 'react'
import type { ComponentType } from 'react'
import {
  Dog, MoonStar, Ghost, Bomb, Siren, HeartPulse,
  TriangleAlert, PartyPopper, Wind, Laugh, ThumbsUp, UsersRound,
  Music, Waves, Tornado, Footprints, BedDouble, VolumeX, Rewind,
} from 'lucide-react'
import type { LucideProps } from 'lucide-react'
import './SoundPanel.css'

interface Props {
  sendIntent: (payload: Record<string, unknown>) => void
  playerName: string
}

interface SoundDef {
  id: string
  icon: ComponentType<LucideProps>
  label: string
  /** Hex accent color — used for icon stroke and subtle button tint */
  color: string
}

const SOUNDS: SoundDef[] = [
  { id: 'howl',      icon: Dog,           label: 'Howl',   color: '#c084fc' },
  { id: 'wolfcry',   icon: MoonStar,      label: 'Moon',   color: '#fbbf24' },
  { id: 'spooky',    icon: Ghost,         label: 'Spooky', color: '#818cf8' },
  { id: 'boom',      icon: Bomb,          label: 'Boom',   color: '#f87171' },
  { id: 'siren',     icon: Siren,         label: 'Siren',  color: '#ef4444' },
  { id: 'ambulance', icon: HeartPulse,    label: 'Ambo',   color: '#f472b6' },
  { id: 'warning',   icon: TriangleAlert, label: 'Warn',   color: '#facc15' },
  { id: 'surprise',  icon: PartyPopper,   label: 'Party',  color: '#fb923c' },
  { id: 'gasp',      icon: Wind,          label: 'Gasp',   color: '#67e8f9' },
  { id: 'laugh',     icon: Laugh,         label: 'LOL',    color: '#a3e635' },
  { id: 'clap',      icon: ThumbsUp,      label: 'Clap',   color: '#34d399' },
  { id: 'people',    icon: UsersRound,    label: 'Crowd',  color: '#38bdf8' },
  { id: 'fail',      icon: Music,         label: 'Fail',   color: '#a78bfa' },
  { id: 'burp',      icon: Waves,         label: 'Burp',   color: '#86efac' },
  { id: 'fart',      icon: Tornado,       label: 'Fart',   color: '#d4d4d8' },
  { id: 'walk',      icon: Footprints,    label: 'Walk',   color: '#7dd3fc' },
  { id: 'snoring',   icon: BedDouble,     label: 'Snore',  color: '#94a3b8' },
  { id: 'shush',     icon: VolumeX,       label: 'Shush',  color: '#fb7185' },
  { id: 'flashback', icon: Rewind,        label: 'Flash',  color: '#f59e0b' },
]

const COOLDOWN_MS = 4000

export default function SoundPanel({ sendIntent, playerName }: Props) {
  const [cooldown, setCooldown] = useState(false)
  const audioCtxRef = useRef<AudioContext | null>(null)

  function playLocalBeep() {
    audioCtxRef.current ??= new AudioContext()
    const ctx = audioCtxRef.current
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.type = 'sine'
    osc.frequency.value = 440
    const now = ctx.currentTime
    gain.gain.setValueAtTime(0.25, now)
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.04)
    osc.start(now)
    osc.stop(now + 0.04)
  }

  const handleSound = useCallback((soundId: string) => {
    if (cooldown) return
    playLocalBeep()
    sendIntent({ type: 'trigger_sound', sound_id: soundId, player_name: playerName })
    setCooldown(true)
    setTimeout(() => setCooldown(false), COOLDOWN_MS)
  }, [cooldown, sendIntent, playerName]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="sound-panel" role="toolbar" aria-label="Sound board">
      <div className="sound-panel__scroll">
        {SOUNDS.map(({ id, icon: Icon, label, color }) => (
          <button
            key={id}
            className={`sound-panel__btn${cooldown ? ' sound-panel__btn--cooldown' : ''}`}
            style={{ '--btn-accent': color, '--btn-bg': `${color}18` } as React.CSSProperties}
            onClick={() => handleSound(id)}
            aria-label={label}
            disabled={cooldown}
          >
            <span className="sound-panel__icon">
              <Icon size={20} strokeWidth={1.8} color={color} />
            </span>
            <span className="sound-panel__label">{label}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
