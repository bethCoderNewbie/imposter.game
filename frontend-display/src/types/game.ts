// TypeScript types mirroring backend-engine/engine/state/models.py + enums.py
// Do not add fields not present in the server's StrippedState output.

export type Phase =
  | 'lobby'
  | 'role_deal'
  | 'night'
  | 'day'
  | 'day_vote'
  | 'hunter_pending'
  | 'game_over'

export type Team = 'village' | 'werewolf' | 'neutral'
export type InvestigationResult = 'village' | 'wolf' | 'neutral'

export interface GameConfig {
  night_timer_seconds: number
  day_timer_seconds: number
  vote_timer_seconds: number
  role_deal_timer_seconds: number
  hunter_pending_timer_seconds: number
  player_count: number
  roles: Record<string, number>
}

export interface PlayerState {
  player_id: string
  display_name: string
  avatar_id: string
  is_connected: boolean
  role: string | null
  team: Team | null
  is_alive: boolean
  night_action_submitted: boolean
  role_confirmed: boolean
  vote_target_id: string | null
  puzzles_solved_count?: number
}

export interface PuzzleState {
  active: boolean
  puzzle_type: string
  puzzle_data: Record<string, unknown>
  time_limit_seconds: number
  solved: boolean | null
}

export interface NightActions {
  actions_submitted_count: number
  actions_required_count: number
  // Role-specific — only present in that role's stripped view
  seer_target_id?: string | null
  seer_result?: InvestigationResult | null
  wolf_votes?: Record<string, string>
  tracker_target_id?: string | null
  tracker_result?: string[]
  puzzle_state?: PuzzleState | null
  // Villager view only (ADR-003 §8)
  decoy_reveal_delay_ms?: number
}

export interface EliminationEvent {
  round: number
  phase: string
  player_id: string
  cause: string
  role: string | null
  saved_by_doctor: boolean
}

export interface TimelineEvent {
  round: number
  phase: string
  event_type: string
  actor_id: string | null
  target_id: string | null
  display_text: string
}

export interface PostMatch {
  timeline: TimelineEvent[]
  winner: string
  rounds_played: number
}

export interface StrippedGameState {
  game_id: string
  schema_version: string
  phase: Phase
  round: number
  host_player_id: string
  timer_ends_at: string | null
  config: GameConfig
  players: Record<string, PlayerState>
  night_actions: NightActions
  day_votes: Record<string, string>
  elimination_log: EliminationEvent[]
  winner: string | null
  winner_player_id: string | null
  // View-specific fields
  seer_knowledge?: Record<string, InvestigationResult>
  tracker_knowledge?: Record<string, string[]>
  post_match?: PostMatch | null
  role_registry?: Record<string, Record<string, unknown>>
}

export interface SyncMessage {
  type: 'sync'
  state_id: number
  schema_version: string
  state: StrippedGameState
}

export interface UpdateMessage {
  type: 'update'
  state_id: number
  schema_version: string
  state: StrippedGameState
}

export interface ErrorMessage {
  type: 'error'
  code: string
  message: string
}

export interface PlayerRosterEntry {
  player_id: string
  display_name: string
  avatar_id: string
  is_connected: boolean
}

export interface MatchDataMessage {
  type: 'match_data'
  players: PlayerRosterEntry[]
}

export type ServerMessage = SyncMessage | UpdateMessage | MatchDataMessage | ErrorMessage

// Avatar color palette — 8 preset colors for avatar_01…avatar_08
export const AVATAR_COLORS: Record<string, string> = {
  avatar_01: '#e57373',
  avatar_02: '#4db6ac',
  avatar_03: '#7986cb',
  avatar_04: '#ffb74d',
  avatar_05: '#81c784',
  avatar_06: '#f06292',
  avatar_07: '#64b5f6',
  avatar_08: '#ba68c8',
}

export function getAvatarColor(avatarId: string): string {
  return AVATAR_COLORS[avatarId] ?? '#718096'
}

export function getInitials(displayName: string): string {
  return displayName.slice(0, 2).toUpperCase()
}
