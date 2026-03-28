import { create } from 'zustand'
import type { PlayerRosterEntry } from '../types/game'

interface GameStore {
  roster: PlayerRosterEntry[]
  setRoster: (players: PlayerRosterEntry[]) => void
}

export const useGameStore = create<GameStore>((set) => ({
  roster: [],
  setRoster: (players) => set({ roster: players }),
}))
