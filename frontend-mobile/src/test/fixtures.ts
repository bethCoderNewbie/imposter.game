import type {
  StrippedGameState,
  PlayerState,
  GameConfig,
  NightActions,
  EliminationEvent,
} from '../types/game'

export function makePlayer(overrides: Partial<PlayerState> = {}): PlayerState {
  return {
    player_id: 'p1',
    display_name: 'Alice',
    avatar_id: 'avatar_01',
    is_connected: true,
    role: null,
    team: null,
    is_alive: true,
    night_action_submitted: false,
    role_confirmed: false,
    vote_target_id: null,
    ...overrides,
  }
}

const DEFAULT_CONFIG: GameConfig = {
  night_timer_seconds: 60,
  day_timer_seconds: 180,
  vote_timer_seconds: 90,
  role_deal_timer_seconds: 30,
  hunter_pending_timer_seconds: 30,
  player_count: 5,
  roles: { werewolf: 1, villager: 3, seer: 1 },
  difficulty_level: 'standard',
}

const DEFAULT_NIGHT_ACTIONS: NightActions = {
  actions_submitted_count: 0,
  actions_required_count: 2,
}

export function makeGameState(overrides: Partial<StrippedGameState> = {}): StrippedGameState {
  const defaultPlayers: Record<string, PlayerState> = {
    p1: makePlayer({ player_id: 'p1', display_name: 'Alice', avatar_id: 'avatar_01' }),
    p2: makePlayer({ player_id: 'p2', display_name: 'Bob',   avatar_id: 'avatar_02' }),
    p3: makePlayer({ player_id: 'p3', display_name: 'Carol', avatar_id: 'avatar_03' }),
    p4: makePlayer({ player_id: 'p4', display_name: 'Dave',  avatar_id: 'avatar_04' }),
    p5: makePlayer({ player_id: 'p5', display_name: 'Eve',   avatar_id: 'avatar_05' }),
  }
  return {
    game_id: 'test-game-001',
    schema_version: '0.4',
    phase: 'lobby',
    round: 1,
    host_player_id: 'p1',
    timer_ends_at: null,
    config: DEFAULT_CONFIG,
    players: defaultPlayers,
    night_actions: DEFAULT_NIGHT_ACTIONS,
    day_votes: {},
    elimination_log: [],
    winner: null,
    winner_player_id: null,
    ...overrides,
  }
}

export function makeElimination(overrides: Partial<EliminationEvent> = {}): EliminationEvent {
  return {
    round: 1,
    phase: 'night',
    player_id: 'p2',
    cause: 'wolf_kill',
    role: null,
    saved_by_doctor: false,
    ...overrides,
  }
}
