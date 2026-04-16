// TypeScript types mirroring backend-engine/engine/state/models.py + enums.py
// Duplicated from frontend-display — no shared package (two independent apps).

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
  difficulty_level: 'easy' | 'standard' | 'hard'
}

export interface PlayerState {
  player_id: string
  display_name: string
  avatar_id: string
  photo_url?: string | null
  is_connected: boolean
  role: string | null
  team: Team | null
  is_alive: boolean
  night_action_submitted: boolean
  role_confirmed: boolean
  vote_target_id: string | null
  puzzles_solved_count?: number
  doused_player_ids?: string[]  // Arsonist only — own player strip
  witch_heal_used?: boolean          // Witch only — own player strip
  witch_kill_used?: boolean          // Witch only — own player strip
  lunatic_redirect_used?: boolean    // Lunatic only — own player strip
  puzzle_state?: PuzzleState | null
  grid_puzzle_state?: PuzzleState | null
  under_attack?: boolean   // own player only — true while a wolf is charging their quadrant
}

export interface PuzzleState {
  active: boolean
  puzzle_type: string  // "logic" | "math" | "sequence"
  puzzle_data: Record<string, unknown>
  time_limit_seconds: number
  solved: boolean | null
  hint_pending?: boolean
}

export interface SonarPingResult {
  quadrant: 'top_left' | 'top_right' | 'bottom_left' | 'bottom_right'
  heat: number
  tier_counts: Record<string, number>
}

export interface GridActivityEntry {
  row: number
  col: number
  quadrant: 'top_left' | 'top_right' | 'bottom_left' | 'bottom_right'
  sequence_idx: number
}

export interface NightActions {
  actions_submitted_count: number
  actions_required_count: number
  seer_target_id?: string | null
  seer_result?: InvestigationResult | null
  wolf_votes?: Record<string, string>
  tracker_target_id?: string | null
  tracker_result?: string[]
  decoy_reveal_delay_ms?: number
  // Grid system
  grid_layout?: number[][] | null        // 5×5 tier grid (1/2/3). Public.
  grid_activity?: GridActivityEntry[]    // Wolf view only — anonymized activity log
  sonar_pings_used?: number             // Public
  sonar_ping_results?: SonarPingResult[] // Wolf view only
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
  timer_paused?: boolean
  timer_remaining_seconds?: number | null
  config: GameConfig
  players: Record<string, PlayerState>
  night_actions: NightActions
  day_votes: Record<string, string>
  elimination_log: EliminationEvent[]
  winner: string | null
  winner_player_id: string | null
  seer_knowledge?: Record<string, InvestigationResult>
  tracker_knowledge?: Record<string, string[]>
  village_powers_cursed?: boolean
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

export interface HintPayload {
  type: 'hint_reward'
  hint_id: string
  category: string
  text: string
  round: number
  expires_after_round: number | null
  source: 'archive' | 'grid'
}

export interface RedirectMessage {
  type: 'redirect'
  new_game_id: string | null
  players: Record<string, { new_player_id: string; new_session_token: string }>
}

export interface PlayerRosterEntry {
  player_id: string
  display_name: string
  avatar_id: string
  photo_url?: string | null
  is_connected: boolean
}

export interface MatchDataMessage {
  type: 'match_data'
  players: PlayerRosterEntry[]
}

export interface GridRippleMessage {
  type: 'grid_ripple'
  quadrant: 'top_left' | 'top_right' | 'bottom_left' | 'bottom_right'
  tier: 1 | 2 | 3
}

export type ServerMessage = SyncMessage | UpdateMessage | ErrorMessage | HintPayload | RedirectMessage | MatchDataMessage | GridRippleMessage

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

// Role color map for mobile RoleRevealScreen background (ADR-003 §5)
export const ROLE_COLORS: Record<string, string> = {
  werewolf:    'var(--role-wolf)',
  alpha_wolf:  'var(--role-wolf)',
  wolf_shaman: 'var(--role-wolf)',
  infector:    'var(--role-wolf)',
  seer:        'var(--role-seer)',
  tracker:     'var(--role-seer)',
  doctor:      'var(--role-doctor)',
  villager:    'var(--role-villager)',
  mayor:       'var(--role-villager)',
  hunter:      'var(--role-villager)',
  cupid:       'var(--role-villager)',
  jester:      '#d4a017',
  arsonist:    '#c05621',
  serial_killer: '#2d3748',
  framer:      'var(--role-wolf)',
  witch:       '#553399',
  lunatic:     '#2d3748',
  wise:        '#b7791f',
  bodyguard:   '#2b6cb0',
  ghost:       '#4a5568',
}

export function getRoleColor(role: string): string {
  return ROLE_COLORS[role] ?? 'var(--role-villager)'
}

// Wolf team roles — used by NightActionShell to route to WolfVoteUI
export const WOLF_ROLES = new Set(['werewolf', 'alpha_wolf', 'wolf_shaman', 'framer', 'infector'])
