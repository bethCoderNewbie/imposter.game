import type { DifficultyLevel } from '../../types/game'

export function formatSeconds(s: number): string {
  const m = Math.floor(s / 60)
  const rem = s % 60
  return m > 0 ? `${m}:${String(rem).padStart(2, '0')}` : `${s}s`
}

export const DIFFICULTY_LABELS: Record<DifficultyLevel, string> = {
  easy: 'Easy', standard: 'Balanced', hard: 'Hard',
}

export const TIMER_STEPS: Record<string, number> = {
  night_timer_seconds: 15,
  day_timer_seconds: 30,
  vote_timer_seconds: 15,
}

export const TIMER_BOUNDS: Record<string, [number, number]> = {
  night_timer_seconds:  [30,  120],
  day_timer_seconds:    [60,  300],
  vote_timer_seconds:   [30,  120],
}

export const TIMER_LABELS: Record<string, string> = {
  night_timer_seconds: 'Night',
  day_timer_seconds:   'Day',
  vote_timer_seconds:  'Vote',
}

export const TIMER_FIELDS = ['night_timer_seconds', 'day_timer_seconds', 'vote_timer_seconds'] as const
export type TimerField = typeof TIMER_FIELDS[number]

export const DEFAULT_CONFIG = {
  difficulty_level: 'standard' as DifficultyLevel,
  night_timer_seconds: 60,
  day_timer_seconds: 180,
  vote_timer_seconds: 90,
}

export const VOICE_LABELS: Record<string, string> = {
  uncle_fu:           'Uncle Fu',
  kokoro:             'Kokoro',
  'cosyvoice-marvin': 'Marvin',
}

export function voiceLabel(id: string): string {
  return VOICE_LABELS[id] ?? id.replace(/[_-]/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}
