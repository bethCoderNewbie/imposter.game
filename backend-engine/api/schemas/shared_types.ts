/**
 * shared_types.ts — TypeScript equivalents of all Pydantic models.
 * Source of truth: backend-engine/engine/state/models.py
 * Both frontends copy this file to src/types/game_state.ts
 * Schema version: 0.4
 */

// ── Enums ────────────────────────────────────────────────────────────────────

export type Phase =
  | "lobby"
  | "role_deal"
  | "night"
  | "day"
  | "day_vote"
  | "hunter_pending"
  | "game_over";

export type Team = "village" | "werewolf" | "neutral";

export type InvestigationResult = "village" | "wolf" | "neutral";

export type EliminationCause =
  | "wolf_kill"
  | "day_vote"
  | "serial_killer"
  | "arsonist"
  | "hunter_revenge"
  | "lovers_chain"
  | "infector_convert";

export type WinCondition =
  | "village_wins"
  | "werewolf_wins"
  | "jester_wins"
  | "serial_killer_wins"
  | "arsonist_wins"
  | "lovers_win";

export type DifficultyLevel = "easy" | "standard" | "hard";

// ── Game Config ──────────────────────────────────────────────────────────────

export interface GameConfig {
  night_timer_seconds: number;
  day_timer_seconds: number;
  vote_timer_seconds: number;
  role_deal_timer_seconds: number;
  hunter_pending_timer_seconds: number;
  player_count: number;
  roles: Record<string, number>; // role_id -> count
  difficulty_level: DifficultyLevel;
}

// ── Player State ─────────────────────────────────────────────────────────────

export interface PlayerState {
  player_id: string;
  display_name: string;
  avatar_id: string;
  is_connected: boolean;
  /** null until role_deal phase; null for other players in display/village view */
  role: string | null;
  /** null until role_deal phase; null for other players in display/village view */
  team: Team | null;
  is_alive: boolean;
  night_action_submitted: boolean;
  role_confirmed: boolean;
  /** convenience ref — your own vote target */
  vote_target_id: string | null;
  /** Arsonist only — own view */
  doused_player_ids: string[];
  /** Cupid-linked players only */
  lovers_partner_id: string | null;
  /** own player only */
  puzzles_solved_count: number;
  /** own player only; correct_index stripped before broadcast */
  puzzle_state: PuzzleState | null;
  // Server-only fields (never sent to clients):
  // is_protected, last_protected_player_id, session_token,
  // hunter_fired, is_framed_tonight, hints_received, infect_used
}

// ── Night Actions ─────────────────────────────────────────────────────────────

export interface NightActions {
  /** Wolf team only: wolf_pid -> target_pid */
  wolf_votes: Record<string, string>;

  /** Seer only */
  seer_target_id: string | null;
  /** Seer only: set after resolution */
  seer_result: InvestigationResult | null;

  /** Serial Killer only (until game_over) */
  serial_killer_target_id: string | null;

  /** Arsonist only */
  arsonist_action: "douse" | "ignite" | null;
  arsonist_douse_target_id: string | null;

  /** Tracker only */
  tracker_target_id: string | null;
  tracker_result: string[];

  /** Public — all clients see these for progress display */
  actions_submitted_count: number;
  actions_required_count: number;

  // Server-only fields (never sent to clients):
  // roleblock_target_id, doctor_target_id, roleblocked_player_id,
  // false_hint_queued, false_hint_payload, infector_target_id,
  // framer_action, framer_target_id, cupid_link
}

// ── Puzzle State ──────────────────────────────────────────────────────────────

export interface PuzzleState {
  active: boolean;
  puzzle_type: "math" | "logic" | "sequence";
  /** correct_index is stripped before send — never present on client */
  puzzle_data: Record<string, unknown>;
  time_limit_seconds: number;
  solved: boolean | null;
  hint_pending: boolean;
}

// ── Elimination & Timeline ────────────────────────────────────────────────────

export interface EliminationEvent {
  round: number;
  phase: "night" | "day";
  player_id: string;
  cause: EliminationCause;
  /** null during live play; revealed at game_over */
  role: string | null;
  /** only present in game_over broadcast */
  saved_by_doctor: boolean;
}

export interface TimelineEvent {
  round: number;
  phase: string;
  event_type: string;
  actor_id: string | null;
  target_id: string | null;
  display_text: string;
}

export interface PostMatch {
  timeline: TimelineEvent[];
  winner: string;
  rounds_played: number;
}

// ── Master Game State ─────────────────────────────────────────────────────────

export interface MasterGameState {
  game_id: string;
  schema_version: string;
  seed: string;
  phase: Phase;
  round: number;
  host_player_id: string;
  /** ISO8601 UTC timestamp | null if phase has no timer */
  timer_ends_at: string | null;
  config: GameConfig;
  /** player_id -> PlayerState (fields stripped per viewer) */
  players: Record<string, PlayerState>;
  night_actions: NightActions;
  /** voter_pid -> target_pid (visible during day_vote phase) */
  day_votes: Record<string, string>;
  elimination_log: EliminationEvent[];
  /** null until game_over */
  winner: Team | null;
  /** null unless a neutral solo role wins */
  winner_player_id: string | null;
  /** Seer only: target_pid -> InvestigationResult — accumulated across rounds */
  seer_knowledge: Record<string, InvestigationResult>;
  /** [pid_a, pid_b] — revealed to linked players; null for all others until game_over */
  lovers_pair: [string, string] | null;
  /** Tracker only: round_str -> [pids_who_visited_tracker_target] */
  tracker_knowledge: Record<string, string[]>;
  /** Role definitions sent to clients (client-safe: no internal balance weights) */
  role_registry: Record<string, unknown>;
  /** null until game_over */
  post_match: PostMatch | null;
  /** Monotonic version counter — increment confirms state receipt */
  state_id: number;
}

// ── WebSocket Messages ────────────────────────────────────────────────────────

/** Sent by server on initial connect — full state baseline */
export interface SyncMessage {
  type: "sync";
  state_id: number;
  schema_version: string;
  state: MasterGameState;
}

/** Sent by server on every game-event broadcast */
export interface UpdateMessage {
  type: "update";
  state_id: number;
  schema_version: string;
  state: MasterGameState;
}

/** Sent by server on validation errors */
export interface ErrorMessage {
  type: "error";
  code: string;
  message: string;
}

/** Sent by server on lobby player joins/rejoins — roster-only, no secret fields */
export interface PlayerRosterEntry {
  player_id: string;
  display_name: string;
  avatar_id: string;
  is_connected: boolean;
}

export interface MatchDataMessage {
  type: "match_data";
  players: PlayerRosterEntry[];
}

/** Sent by server to deliver puzzle hints */
export interface HintRewardMessage {
  type: "hint_reward";
  hint_id: string;
  category: string;
  text: string;
  round: number;
  expires_after_round: number | null;
}

/** Union of all server-to-client messages */
export type ServerMessage = SyncMessage | UpdateMessage | MatchDataMessage | ErrorMessage | HintRewardMessage;

// ── Intent Payloads (client → server) ────────────────────────────────────────

export interface AuthIntent {
  type: "auth";
  session_token: string;
}

export interface StartGameIntent {
  type: "start_game";
  player_id: string;
  state_id: number;
}

export interface ConfirmRoleRevealIntent {
  type: "confirm_role_reveal";
  player_id: string;
  state_id: number;
}

export interface SubmitNightActionIntent {
  type: "submit_night_action";
  player_id: string;
  state_id: number;
  target_id?: string;
  secondary_target_id?: string;
  wolf_vote_target_id?: string;
  framer_action?: "frame" | "hack_archives";
  false_hint_category?: string;
  false_hint_text?: string;
  arsonist_action?: "douse" | "ignite";
  link_target_a?: string;
  link_target_b?: string;
  answer_index?: number;
  answer_sequence?: number[];
}

export interface SubmitDayVoteIntent {
  type: "submit_day_vote";
  player_id: string;
  state_id: number;
  target_id: string;
}

export interface HunterRevengeIntent {
  type: "hunter_revenge";
  player_id: string;
  state_id: number;
  target_id: string;
}

export interface SubmitPuzzleAnswerIntent {
  type: "submit_puzzle_answer";
  player_id: string;
  state_id: number;
  answer_index?: number;
  answer_sequence?: number[];
}

export interface AdvancePhaseIntent {
  type: "advance_phase";
  player_id: string;
  state_id: number;
}

export type ClientIntent =
  | AuthIntent
  | StartGameIntent
  | ConfirmRoleRevealIntent
  | SubmitNightActionIntent
  | SubmitDayVoteIntent
  | HunterRevengeIntent
  | SubmitPuzzleAnswerIntent
  | AdvancePhaseIntent;
