from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from engine.state.enums import (
    ActionPhase,
    ActionType,
    DifficultyLevel,
    EliminationCause,
    InvestigationResult,
    Phase,
    Team,
    WinCondition,
)


class RoleDefinition(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    name: str
    team: Team
    investigation_result: InvestigationResult = Field(alias="investigationResult")
    wake_order: int = Field(alias="wakeOrder")
    action_phase: ActionPhase = Field(alias="actionPhase")
    action_type: ActionType = Field(alias="actionType")
    max_uses: int | None = Field(default=None, alias="maxUses")
    description: str
    abilities: list[str]
    ui_prompt_night: str = Field(default="", alias="uiPromptNight")
    win_condition: str = Field(alias="winCondition")
    balance_weight: int = Field(alias="balanceWeight")
    ui: dict[str, Any] = Field(default_factory=dict)
    can_be_blocked: bool = Field(default=True, alias="canBeBlocked")

    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)


class GameConfig(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    night_timer_seconds: int = 60
    day_timer_seconds: int = 180
    vote_timer_seconds: int = 90
    role_deal_timer_seconds: int = 30
    hunter_pending_timer_seconds: int = 30
    player_count: int
    roles: dict[str, int]  # role_id -> count
    difficulty_level: DifficultyLevel = DifficultyLevel.STANDARD
    narrator_voice: str = "uncle_fu"  # subdir under api/narrator/audio/


class PuzzleState(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    active: bool = True
    puzzle_type: str  # "math" | "logic" | "sequence"
    puzzle_data: dict[str, Any]  # correct_index is present here but stripped before send
    time_limit_seconds: int
    solved: bool | None = None
    hint_pending: bool = False


class PlayerState(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    player_id: str
    display_name: str
    avatar_id: str = "default_01"
    photo_url: str | None = None
    is_connected: bool = True
    role: str | None = None          # populated after role_deal
    team: Team | None = None         # populated after role_deal
    is_alive: bool = True
    is_protected: bool = False       # server-only: stripped before broadcast
    last_protected_player_id: str | None = None  # server-only
    night_action_submitted: bool = False
    role_confirmed: bool = False
    vote_target_id: str | None = None   # current day vote target (convenience ref)
    session_token: str | None = None    # server-only: stripped before broadcast
    hunter_fired: bool = False          # server-only
    is_framed_tonight: bool = False     # server-only: reset each night
    doused_player_ids: list[str] = Field(default_factory=list)  # Arsonist only
    infect_used: bool = False           # server-only
    witch_heal_used: bool = False       # server-only: stripped from non-witch views
    witch_kill_used: bool = False       # server-only: stripped from non-witch views
    lunatic_redirect_used: bool = False # server-only: stripped from non-lunatic views
    wise_shield_used: bool = False      # server-only: one-use wolf-kill deflection
    lovers_partner_id: str | None = None  # linked players only
    puzzles_solved_count: int = 0       # own player only
    hints_received: list[str] = Field(default_factory=list)  # server-only
    puzzle_state: PuzzleState | None = None  # own player only; correct_index stripped before broadcast
    permanent_id: str | None = None    # server-only: cross-game registry key, never broadcast
    # Grid system fields (server-only during night phase)
    grid_node_row: int | None = None       # server-only: current grid node row
    grid_node_col: int | None = None       # server-only: current grid node column
    grid_puzzle_state: PuzzleState | None = None  # active grid node puzzle; correct_index stripped
    under_attack: bool = False             # own player only: True while a wolf is charging their quadrant


class FalseHintPayload(BaseModel):
    hint_id: str
    category: str
    text: str
    round: int
    expires_after_round: int | None = None
    is_fabricated: bool = True          # server-only; stripped before delivery


class NightActions(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    # Wolf team
    wolf_votes: dict[str, str] = Field(default_factory=dict)  # wolf_pid -> target_pid
    roleblock_target_id: str | None = None   # server-only

    # Seer
    seer_target_id: str | None = None        # seer-only
    seer_result: InvestigationResult | None = None  # seer-only

    # Doctor
    doctor_target_id: str | None = None      # server-only

    # Serial Killer
    serial_killer_target_id: str | None = None  # SK-only until game_over

    # Framer
    framer_action: str | None = None         # server-only: "frame" | "hack_archives"
    framer_target_id: str | None = None      # server-only
    false_hint_queued: bool = False          # server-only
    false_hint_payload: FalseHintPayload | None = None  # server-only

    # Arsonist
    arsonist_action: str | None = None       # Arsonist-only: "douse" | "ignite"
    arsonist_douse_target_id: str | None = None  # Arsonist-only

    # Infector
    infector_target_id: str | None = None    # server-only

    # Cupid
    cupid_link: list[str] | None = None      # server-only during resolution

    # Tracker
    tracker_target_id: str | None = None     # Tracker-only
    tracker_result: list[str] = Field(default_factory=list)  # Tracker-only

    # Witch
    witch_action: str | None = None           # server-only: "heal" | "kill"
    witch_target_id: str | None = None        # server-only

    # Bodyguard
    bodyguard_target_id: str | None = None    # server-only

    # Lunatic
    lunatic_redirect: bool = False            # server-only: activated redirect this night

    # Computed at resolution step 1
    roleblocked_player_id: str | None = None  # server-only

    # Aggregate counts (public — display client sees these)
    actions_submitted_count: int = 0
    actions_required_count: int = 0

    # Grid system — populated at NIGHT phase entry
    grid_layout: list[list[int]] | None = None
    # 5×5 tier grid. 1=green(5s), 2=yellow(10s), 3=red(20s). Public — no secrets in tier map.

    grid_activity: list[dict[str, Any]] = Field(default_factory=list)
    # [{row, col, quadrant, sequence_idx}] — anonymized completed-node log.
    # quadrant: "top_left"|"top_right"|"bottom_left"|"bottom_right"
    # Wolf view ONLY (stripped from all other views).

    sonar_pings_used: int = 0
    # Total Sonar Pings wolves fired this night. Public.

    sonar_ping_results: list[dict[str, Any]] = Field(default_factory=list)
    # [{quadrant, heat, tier_counts}] — results of wolf sonar pings. Wolf view ONLY.

    night_action_change_count: dict[str, int] = Field(default_factory=dict)
    # player_id -> total intent submissions this night. SERVER-ONLY — never sent to any client.

    wolf_charges: dict[str, dict[str, int]] = Field(default_factory=dict)
    # wolf_pid -> {quadrant -> accumulated_ms}. Tracks cumulative hold time per wolf per quadrant.
    # SERVER-ONLY — never sent to any client. Reset at NIGHT entry and when charge fires or is defended.

    charge_kill_target_id: str | None = None
    # Set when the pack's combined charge for a quadrant reaches CHARGE_THRESHOLD_MS and hits an active solver.
    # Processed by resolve_night() as the wolf kill — takes priority over wolf_votes.
    # SERVER-ONLY — always stripped. Reset at NIGHT entry.



class EliminationEvent(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    round: int
    phase: str  # "night" | "day"
    player_id: str
    cause: EliminationCause
    role: str | None = None          # null during live play; revealed at game_over
    saved_by_doctor: bool = False    # game_over broadcast only


class TimelineEvent(BaseModel):
    round: int
    phase: str
    event_type: str
    actor_id: str | None = None
    target_id: str | None = None
    display_text: str


class PostMatch(BaseModel):
    timeline: list[TimelineEvent] = Field(default_factory=list)
    winner: str
    rounds_played: int


class MasterGameState(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    game_id: str
    schema_version: str = "0.4"
    seed: str
    phase: Phase = Phase.LOBBY
    round: int = 0
    host_player_id: str | None = None
    timer_ends_at: str | None = None  # ISO8601 UTC | null
    timer_paused: bool = False
    timer_remaining_seconds: int | None = None
    config: GameConfig
    players: dict[str, PlayerState] = Field(default_factory=dict)  # player_id -> PlayerState
    night_actions: NightActions = Field(default_factory=NightActions)
    day_votes: dict[str, str] = Field(default_factory=dict)  # voter_pid -> target_pid
    elimination_log: list[EliminationEvent] = Field(default_factory=list)
    winner: str | None = None   # "village" | "werewolf" | "neutral" | "draw" | null
    winner_player_id: str | None = None  # neutral solo wins only
    seer_knowledge: dict[str, str] = Field(default_factory=dict)  # target_pid -> InvestigationResult
    hunter_queue: list[str] = Field(default_factory=list)  # hunter player_ids pending revenge
    lovers_pair: list[str] | None = None  # [pid_a, pid_b]
    tracker_knowledge: dict[str, list[str]] = Field(default_factory=dict)  # round_str -> [pids]
    role_registry: dict[str, dict[str, Any]] = Field(default_factory=dict)  # sent to clients
    post_match: PostMatch | None = None
    lunatic_cursed_wolf_id: str | None = None  # server-only: wolf cursed by Lunatic sacrifice
    village_powers_cursed: bool = False        # public: set when Wise is burned at the stake

    # Monotonic version counter — incremented on every state mutation
    state_id: int = 0

    # Server-only — stripped before every broadcast, never sent to any client
    host_secret: str | None = None
    # Server-only: populated by /rematch so disconnected players receive redirect on WS reconnect
    rematch_redirect: dict[str, Any] | None = None
