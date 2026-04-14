"""
Intent handlers: one async function per intent type.
Each validates phase, player status, business rules — then calls pure resolver functions.
All raise IntentError on invalid intents.
"""

from __future__ import annotations

import asyncio
import secrets
from typing import Any
from uuid import uuid4

from api.intents.errors import IntentError
from api.narrator.triggers import narrate, narrate_sequence
from api.timer_tasks import cancel_phase_timer, start_phase_timer
from engine.phases.machine import should_auto_advance, transition_phase
from engine.resolver.day import resolve_day_vote
from engine.resolver.hunter import HunterError, resolve_hunter_revenge, resolve_hunter_timeout
from engine.resolver.night import resolve_night
from engine.resolver.puzzle import PuzzleError, resolve_puzzle_answer
from engine.config import get_settings
from engine.roles_loader import CLIENT_SAFE_ROLE_REGISTRY, ROLE_REGISTRY
from engine.setup import DIFFICULTY_BALANCE_RANGE, assign_roles, build_composition
from engine.state.enums import Phase, Team
from engine.state.models import FalseHintPayload, MasterGameState, PlayerState


def _require_phase(G: MasterGameState, *phases: Phase) -> None:
    if G.phase not in phases:
        raise IntentError(
            "WRONG_PHASE",
            f"Action not allowed in phase '{G.phase}'. Expected: {[p.value for p in phases]}",
        )


def _require_alive(G: MasterGameState, player_id: str) -> PlayerState:
    player = G.players.get(player_id)
    if player is None:
        raise IntentError("PLAYER_NOT_FOUND", f"Player {player_id} not found.")
    if not player.is_alive:
        raise IntentError("DEAD_PLAYER_ACTION", "Dead players cannot submit actions.")
    return player


def _require_host(G: MasterGameState, player_id: str) -> None:
    if player_id != G.host_player_id:
        raise IntentError("NOT_HOST", "Only the host can perform this action.")


async def _maybe_start_timer(G: MasterGameState, game_id: str, queue) -> None:
    """Start a phase timer if the new phase has one."""
    if G.timer_ends_at:
        await start_phase_timer(
            game_id=game_id,
            phase=G.phase,
            timer_ends_at=G.timer_ends_at,
            enqueue_fn=queue.enqueue,
        )


# ── Handlers ──────────────────────────────────────────────────────────────────

async def handle_start_game(G, intent, redis_client, cm) -> MasterGameState:
    _require_phase(G, Phase.LOBBY)
    _require_host(G, intent.get("player_id", ""))

    if len(G.players) < 5:
        raise IntentError("NOT_ENOUGH_PLAYERS", "At least 5 players required to start.")

    # Assign roles
    player_count = len(G.players)
    target_range = DIFFICULTY_BALANCE_RANGE.get(G.config.difficulty_level, [-2, 2])
    composition = build_composition(player_count, G.seed, target_range=target_range)
    role_map = assign_roles(list(G.players.keys()), composition, G.seed)

    G = G.model_copy(deep=True)
    for pid, role_id in role_map.items():
        role_def = ROLE_REGISTRY[role_id]
        G.players[pid].role = role_id
        G.players[pid].team = role_def["team"]

    G.config = G.config.model_copy(update={"roles": composition, "player_count": player_count})
    G = transition_phase(G, Phase.ROLE_DEAL)

    from api.game_queue import get_or_create_queue
    queue = get_or_create_queue(G.game_id)
    await _maybe_start_timer(G, G.game_id, queue)

    if get_settings().narrator_enabled:
        asyncio.create_task(narrate("game_start", G, cm, G.game_id))

    return G


async def handle_confirm_role_reveal(G, intent, redis_client, cm) -> MasterGameState:
    _require_phase(G, Phase.ROLE_DEAL)
    player_id = intent.get("player_id", "")
    player = G.players.get(player_id)
    if player is None:
        raise IntentError("PLAYER_NOT_FOUND", f"Player {player_id} not found.")

    G = G.model_copy(deep=True)
    G.players[player_id].role_confirmed = True

    if should_auto_advance(G):
        cancel_phase_timer(G.game_id)
        G = transition_phase(G, Phase.NIGHT)
        from api.game_queue import get_or_create_queue
        queue = get_or_create_queue(G.game_id)
        await _maybe_start_timer(G, G.game_id, queue)

        if get_settings().narrator_enabled:
            asyncio.create_task(narrate("night_open", G, cm, G.game_id))

    return G


async def handle_submit_night_action(G, intent, redis_client, cm) -> MasterGameState:
    _require_phase(G, Phase.NIGHT)
    player_id = intent.get("player_id", "")
    player = _require_alive(G, player_id)

    if player.night_action_submitted:
        raise IntentError("DUPLICATE_ACTION", "Night action already submitted this round.")

    G = G.model_copy(deep=True)
    player = G.players[player_id]
    role_id = player.role or ""
    na = G.night_actions

    # Route to role-specific action application
    if role_id == "werewolf" or role_id == "alpha_wolf":
        target_id = intent.get("target_id")
        if not target_id or target_id not in G.players:
            raise IntentError("INVALID_TARGET", "Invalid kill target.")
        if G.players[target_id].team == Team.WEREWOLF:
            raise IntentError("INVALID_TARGET", "Wolves cannot vote to kill their teammates.")
        na.wolf_votes[player_id] = target_id
        # Signal display client to play a scream SFX after a random delay.
        # Only on the first wolf vote this night to avoid duplicate screams (PRD-012 §2.3).
        if len(na.wolf_votes) == 1:
            asyncio.create_task(
                cm.broadcast_raw(G.game_id, {"type": "wolf_kill_queued"})
            )

    elif role_id == "wolf_shaman":
        target_id = intent.get("target_id")
        if not target_id or target_id not in G.players:
            raise IntentError("INVALID_TARGET", "Invalid roleblock target.")
        na.roleblock_target_id = target_id
        # Wolf Shaman also participates in wolf vote
        kill_target = intent.get("secondary_target_id") or intent.get("target_id")
        if kill_target:
            na.wolf_votes[player_id] = kill_target

    elif role_id == "seer":
        target_id = intent.get("target_id")
        if not target_id or target_id not in G.players:
            raise IntentError("INVALID_TARGET", "Invalid inspect target.")
        if target_id == player_id:
            raise IntentError("SELF_TARGET", "Cannot inspect yourself.")
        na.seer_target_id = target_id

    elif role_id == "doctor":
        target_id = intent.get("target_id")
        if not target_id or target_id not in G.players:
            raise IntentError("INVALID_TARGET", "Invalid protection target.")
        if player.last_protected_player_id == target_id:
            raise IntentError(
                "CONSECUTIVE_PROTECT_FORBIDDEN",
                "Cannot protect the same player two nights in a row.",
            )
        na.doctor_target_id = target_id

    elif role_id == "serial_killer":
        target_id = intent.get("target_id")
        if not target_id or target_id not in G.players:
            raise IntentError("INVALID_TARGET", "Invalid kill target.")
        if target_id == player_id:
            raise IntentError("SELF_TARGET", "Cannot target yourself.")
        na.serial_killer_target_id = target_id

    elif role_id == "framer":
        framer_action = intent.get("framer_action")
        if framer_action not in ("frame", "hack_archives"):
            raise IntentError("INVALID_ACTION", "framer_action must be 'frame' or 'hack_archives'.")
        na.framer_action = framer_action
        if framer_action == "frame":
            target_id = intent.get("target_id")
            if not target_id or target_id not in G.players:
                raise IntentError("INVALID_TARGET", "Invalid frame target.")
            na.framer_target_id = target_id
        else:
            # hack_archives: server constructs typed payload from client-supplied text fields
            category = intent.get("false_hint_category")
            text = intent.get("false_hint_text")
            if not category or not text:
                raise IntentError(
                    "MISSING_HINT_FIELDS",
                    "false_hint_category and false_hint_text are required for hack_archives.",
                )
            na.false_hint_payload = FalseHintPayload(
                hint_id=str(uuid4()),
                category=category,
                text=text,
                round=G.round,
                expires_after_round=None,
                is_fabricated=True,
            )
        # Framer also participates in wolf vote
        kill_target = intent.get("wolf_vote_target_id")
        if kill_target:
            na.wolf_votes[player_id] = kill_target

    elif role_id == "arsonist":
        arsonist_action = intent.get("arsonist_action")
        if arsonist_action not in ("douse", "ignite"):
            raise IntentError("INVALID_ACTION", "arsonist_action must be 'douse' or 'ignite'.")
        na.arsonist_action = arsonist_action
        if arsonist_action == "douse":
            target_id = intent.get("target_id")
            if not target_id or target_id not in G.players:
                raise IntentError("INVALID_TARGET", "Invalid douse target.")
            if target_id == player_id:
                raise IntentError("SELF_TARGET", "Cannot douse yourself.")
            na.arsonist_douse_target_id = target_id
        elif arsonist_action == "ignite":
            arsonist = G.players[player_id]
            if not arsonist.doused_player_ids:
                raise IntentError("NO_DOUSED_PLAYERS", "No players are doused to ignite.")

    elif role_id == "infector":
        target_id = intent.get("target_id")
        if target_id:
            if target_id not in G.players:
                raise IntentError("INVALID_TARGET", "Invalid infect target.")
            target = G.players[target_id]
            if target.team == Team.WEREWOLF:
                raise IntentError("INVALID_TARGET", "Target is already a werewolf.")
            if player.infect_used:
                raise IntentError("INFECT_USED", "Infector has already used their ability.")
            na.infector_target_id = target_id
        # Also participates in wolf vote
        kill_target = intent.get("wolf_vote_target_id")
        if kill_target:
            na.wolf_votes[player_id] = kill_target

    elif role_id == "cupid":
        if G.round == 1:
            link_a = intent.get("link_target_a")
            link_b = intent.get("link_target_b")
            if not link_a or not link_b or link_a == link_b:
                raise IntentError("INVALID_TARGET", "Cupid must link two different players.")
            if link_a not in G.players or link_b not in G.players:
                raise IntentError("INVALID_TARGET", "One or both link targets not found.")
            na.cupid_link = [link_a, link_b]
        # After round 1: Cupid has no action (decoy puzzle only)

    elif role_id == "tracker":
        target_id = intent.get("target_id")
        if not target_id or target_id not in G.players:
            raise IntentError("INVALID_TARGET", "Invalid track target.")
        if target_id == player_id:
            raise IntentError("SELF_TARGET", "Cannot track yourself.")
        na.tracker_target_id = target_id

    # Mark as submitted and update aggregate count
    player.night_action_submitted = True
    na.actions_submitted_count += 1

    # Auto-advance check
    if should_auto_advance(G):
        cancel_phase_timer(G.game_id)
        elim_count_before = len(G.elimination_log)
        G = resolve_night(G)
        # Broadcast results while still in NIGHT phase so role-specific UIs
        # (Seer, Tracker) can display their outcome before the phase transitions.
        G.state_id += 1
        await cm.broadcast(G.game_id, G)
        if G.phase not in (Phase.GAME_OVER, Phase.HUNTER_PENDING):
            G = transition_phase(G, Phase.DAY)
            if get_settings().narrator_enabled:
                _specs: list = [("night_close", None, None), ("day_open", None, None)]
                if len(G.elimination_log) > elim_count_before:
                    last_elim = G.elimination_log[-1]
                    elim_player = G.players.get(last_elim.player_id)
                    _specs.append(("player_eliminated", elim_player.display_name if elim_player else None, None))
                asyncio.create_task(narrate_sequence(_specs, G, cm, G.game_id))
        from api.game_queue import get_or_create_queue
        queue = get_or_create_queue(G.game_id)
        await _maybe_start_timer(G, G.game_id, queue)

    return G


async def handle_submit_day_vote(G, intent, redis_client, cm) -> MasterGameState:
    _require_phase(G, Phase.DAY_VOTE)
    player_id = intent.get("player_id", "")
    player = _require_alive(G, player_id)

    target_id = intent.get("target_id")
    if not target_id or target_id not in G.players:
        raise IntentError("INVALID_TARGET", "Invalid vote target.")
    if target_id == player_id:
        raise IntentError("SELF_VOTE_NOT_ALLOWED", "Cannot vote to eliminate yourself.")
    if not G.players[target_id].is_alive:
        raise IntentError("TARGET_ALREADY_DEAD", "Cannot vote for an eliminated player.")

    G = G.model_copy(deep=True)
    G.day_votes[player_id] = target_id
    G.players[player_id].vote_target_id = target_id

    if should_auto_advance(G):
        cancel_phase_timer(G.game_id)
        elim_count_before = len(G.elimination_log)
        G = resolve_day_vote(G)
        if get_settings().narrator_enabled:
            _specs: list = []
            if len(G.elimination_log) > elim_count_before:
                last_elim = G.elimination_log[-1]
                elim_player = G.players.get(last_elim.player_id)
                _specs.append(("vote_elimination", elim_player.display_name if elim_player else None, None))
            if G.phase == Phase.GAME_OVER and G.winner is not None:
                _specs.append(("wolves_win" if G.winner == Team.WEREWOLF else "village_wins", None, None))
            if _specs:
                asyncio.create_task(narrate_sequence(_specs, G, cm, G.game_id))
            else:
                asyncio.create_task(narrate("no_elimination", G, cm, G.game_id))
        if G.phase not in (Phase.GAME_OVER, Phase.HUNTER_PENDING):
            G = transition_phase(G, Phase.NIGHT)
            from api.game_queue import get_or_create_queue
            queue = get_or_create_queue(G.game_id)
            await _maybe_start_timer(G, G.game_id, queue)

    return G


async def handle_hunter_revenge(G, intent, redis_client, cm) -> MasterGameState:
    _require_phase(G, Phase.HUNTER_PENDING)
    hunter_id = intent.get("player_id", "")
    target_id = intent.get("target_id", "")

    try:
        G = resolve_hunter_revenge(G, hunter_id, target_id)
    except HunterError as e:
        raise IntentError(e.code, e.message)

    if get_settings().narrator_enabled:
        target = G.players.get(target_id)
        _specs: list = [("hunter_revenge", target.display_name if target else None, None)]
        if G.phase == Phase.GAME_OVER and G.winner is not None:
            _specs.append(("wolves_win" if G.winner == Team.WEREWOLF else "village_wins", None, None))
        asyncio.create_task(narrate_sequence(_specs, G, cm, G.game_id))

    # After hunter resolves, determine next phase
    if G.phase == Phase.HUNTER_PENDING and not G.hunter_queue:
        # Queue drained and game still ongoing — advance to DAY
        G = transition_phase(G, Phase.DAY)
        from api.game_queue import get_or_create_queue
        queue = get_or_create_queue(G.game_id)
        await _maybe_start_timer(G, G.game_id, queue)

    return G


async def handle_submit_puzzle_answer(G, intent, redis_client, cm) -> MasterGameState:
    _require_phase(G, Phase.NIGHT)
    player_id = intent.get("player_id", "")
    _require_alive(G, player_id)

    try:
        G, is_correct = resolve_puzzle_answer(
            G,
            player_id,
            answer_index=intent.get("answer_index"),
            answer_sequence=intent.get("answer_sequence"),
        )
    except PuzzleError as e:
        raise IntentError(e.code, e.message)

    if is_correct:
        # Deliver hint — check if false hint is queued first
        if G.night_actions.false_hint_queued and G.night_actions.false_hint_payload:
            from engine.stripper import strip_fabricated_flag
            false_hint = strip_fabricated_flag(G.night_actions.false_hint_payload.model_dump(mode="json"))
            # Broadcast to ALL wakeOrder==0 players (all receive the same false hint)
            from engine.roles_loader import ROLE_REGISTRY as RR
            for pid, player in G.players.items():
                if player.is_alive and RR.get(player.role or "", {}).get("wakeOrder", -1) == 0:
                    await cm.unicast(G.game_id, pid, {"type": "hint_reward", **false_hint})
        else:
            from engine.puzzle_bank import generate_hint
            await cm.unicast(G.game_id, player_id, generate_hint(G, player_id))

    return G


async def handle_advance_phase(G, intent, redis_client, cm) -> MasterGameState:
    """Host-triggered phase advance (e.g., from DAY discussion to DAY_VOTE)."""
    _require_host(G, intent.get("player_id", ""))
    _require_phase(G, Phase.DAY)

    cancel_phase_timer(G.game_id)
    G = transition_phase(G, Phase.DAY_VOTE)

    if get_settings().narrator_enabled:
        asyncio.create_task(narrate("vote_open", G, cm, G.game_id))

    from api.game_queue import get_or_create_queue
    queue = get_or_create_queue(G.game_id)
    await _maybe_start_timer(G, G.game_id, queue)
    return G


async def handle_phase_timeout(G, intent, redis_client, cm) -> MasterGameState:
    """Timer-triggered phase advancement."""
    timeout_phase = intent.get("phase")
    if timeout_phase != G.phase:
        # Stale timeout — phase already advanced; ignore
        return G

    if G.phase == Phase.ROLE_DEAL:
        # Auto-confirm any unconfirmed players
        G = G.model_copy(deep=True)
        for player in G.players.values():
            player.role_confirmed = True
        G = transition_phase(G, Phase.NIGHT)
        if get_settings().narrator_enabled:
            asyncio.create_task(narrate("night_open", G, cm, G.game_id))

    elif G.phase == Phase.NIGHT:
        elim_count_before = len(G.elimination_log)
        G = resolve_night(G)
        # Same intermediate broadcast as in auto-advance path.
        G.state_id += 1
        await cm.broadcast(G.game_id, G)
        if G.phase not in (Phase.GAME_OVER, Phase.HUNTER_PENDING):
            G = transition_phase(G, Phase.DAY)
            if get_settings().narrator_enabled:
                _specs: list = [("night_close", None, None), ("day_open", None, None)]
                if len(G.elimination_log) > elim_count_before:
                    last_elim = G.elimination_log[-1]
                    elim_player = G.players.get(last_elim.player_id)
                    _specs.append(("player_eliminated", elim_player.display_name if elim_player else None, None))
                asyncio.create_task(narrate_sequence(_specs, G, cm, G.game_id))

    elif G.phase == Phase.DAY:
        G = transition_phase(G, Phase.DAY_VOTE)
        if get_settings().narrator_enabled:
            asyncio.create_task(narrate("vote_open", G, cm, G.game_id))

    elif G.phase == Phase.DAY_VOTE:
        elim_count_before = len(G.elimination_log)
        G = resolve_day_vote(G)
        if get_settings().narrator_enabled:
            _specs: list = []
            if len(G.elimination_log) > elim_count_before:
                last_elim = G.elimination_log[-1]
                elim_player = G.players.get(last_elim.player_id)
                _specs.append(("vote_elimination", elim_player.display_name if elim_player else None, None))
            if G.phase == Phase.GAME_OVER and G.winner is not None:
                _specs.append(("wolves_win" if G.winner == Team.WEREWOLF else "village_wins", None, None))
            if _specs:
                asyncio.create_task(narrate_sequence(_specs, G, cm, G.game_id))
            else:
                asyncio.create_task(narrate("no_elimination", G, cm, G.game_id))
        if G.phase not in (Phase.GAME_OVER, Phase.HUNTER_PENDING):
            G = transition_phase(G, Phase.NIGHT)

    elif G.phase == Phase.HUNTER_PENDING:
        # Auto-resolve: hunter skips revenge
        hunter_id = G.hunter_queue[0] if G.hunter_queue else None
        if hunter_id:
            G = resolve_hunter_timeout(G, hunter_id)
        # resolve_hunter_timeout never changes phase away from HUNTER_PENDING;
        # only check_win_condition can flip it to GAME_OVER. So we must explicitly
        # transition when the queue is drained and game is still ongoing.
        if G.phase == Phase.HUNTER_PENDING and not G.hunter_queue:
            G = transition_phase(G, Phase.DAY)

    from api.game_queue import get_or_create_queue
    queue = get_or_create_queue(G.game_id)
    await _maybe_start_timer(G, G.game_id, queue)
    return G


async def handle_player_disconnected(G, intent, redis_client, cm) -> MasterGameState:
    player_id = intent.get("player_id")
    if player_id and player_id in G.players:
        G = G.model_copy(deep=True)
        G.players[player_id].is_connected = False
    return G
