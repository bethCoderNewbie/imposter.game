"""
Intent handlers: one async function per intent type.
Each validates phase, player status, business rules — then calls pure resolver functions.
All raise IntentError on invalid intents.
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timedelta, timezone as _tz
from typing import Any
from uuid import uuid4

_UTC = _tz.utc
EXTEND_INCREMENT = 30  # seconds added by extend_timer

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
    composition = build_composition(
        player_count, G.seed,
        target_range=target_range,
        difficulty_level=G.config.difficulty_level,
    )
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

    elif role_id == "witch":
        witch_action = intent.get("witch_action")
        if witch_action not in ("heal", "kill", "skip"):
            raise IntentError("INVALID_ACTION", "witch_action must be 'heal', 'kill', or 'skip'.")
        if witch_action != "skip":
            target_id = intent.get("target_id")
            if not target_id or target_id not in G.players:
                raise IntentError("INVALID_TARGET", "Invalid target.")
            if not G.players[target_id].is_alive:
                raise IntentError("INVALID_TARGET", "Cannot target a dead player.")
            if witch_action == "heal":
                if player.witch_heal_used:
                    raise IntentError("POTION_SPENT", "Heal potion already used.")
            elif witch_action == "kill":
                if player.witch_kill_used:
                    raise IntentError("POTION_SPENT", "Kill potion already used.")
                if target_id == player_id:
                    raise IntentError("SELF_TARGET", "Cannot use the kill potion on yourself.")
            na.witch_action = witch_action
            na.witch_target_id = target_id
        # skip: no-op — night_action_submitted is set below

    elif role_id == "bodyguard":
        target_id = intent.get("target_id")
        if not target_id or target_id not in G.players:
            raise IntentError("INVALID_TARGET", "Invalid protection target.")
        if not G.players[target_id].is_alive:
            raise IntentError("INVALID_TARGET", "Cannot protect a dead player.")
        na.bodyguard_target_id = target_id

    elif role_id == "lunatic":
        lunatic_action = intent.get("lunatic_action")
        if lunatic_action not in ("redirect", "skip"):
            raise IntentError("INVALID_ACTION", "lunatic_action must be 'redirect' or 'skip'.")
        if lunatic_action == "redirect":
            if player.lunatic_redirect_used:
                raise IntentError("REDIRECT_USED", "Redirect already used this game.")
            na.lunatic_redirect = True
        # skip: no-op — night_action_submitted is set below

    # Mark as submitted and update aggregate count
    player.night_action_submitted = True
    na.actions_submitted_count += 1

    # Night phase advances only via the timer (phase_timeout intent).
    # Auto-advance on all-actions-done is intentionally disabled so the timer
    # always runs to completion — players cannot observe submission timing.

    return G


async def handle_submit_day_vote(G, intent, redis_client, cm) -> MasterGameState:
    _require_phase(G, Phase.DAY_VOTE)
    player_id = intent.get("player_id", "")
    player = G.players.get(player_id)
    if player is None:
        raise IntentError("PLAYER_NOT_FOUND", f"Player {player_id} not found.")
    if player.role == "ghost":
        if player.is_alive:
            raise IntentError("GHOST_CANNOT_VOTE_ALIVE", "The Ghost cannot vote while alive.")
        # Dead Ghost may vote — no alive requirement
    else:
        if not player.is_alive:
            raise IntentError("DEAD_PLAYER_ACTION", "Dead players cannot submit actions.")

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
            from engine.hint_bank import generate_hint
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


async def handle_pause_timer(G, intent, redis_client, cm) -> MasterGameState:
    """Host pauses the running phase timer."""
    _require_host(G, intent.get("player_id", ""))
    _require_phase(G, Phase.NIGHT, Phase.ROLE_DEAL, Phase.DAY, Phase.DAY_VOTE, Phase.HUNTER_PENDING)
    if G.timer_paused:
        raise IntentError("ALREADY_PAUSED", "Timer is already paused.")
    G = G.model_copy(deep=True)
    remaining = 0
    if G.timer_ends_at:
        deadline = datetime.fromisoformat(G.timer_ends_at.replace("Z", "+00:00"))
        remaining = max(0, int((deadline - datetime.now(_UTC)).total_seconds()))
    cancel_phase_timer(G.game_id)
    G.timer_paused = True
    G.timer_remaining_seconds = remaining
    G.timer_ends_at = None
    return G


async def handle_resume_timer(G, intent, redis_client, cm) -> MasterGameState:
    """Host resumes a paused timer from remaining seconds."""
    _require_host(G, intent.get("player_id", ""))
    _require_phase(G, Phase.NIGHT, Phase.ROLE_DEAL, Phase.DAY, Phase.DAY_VOTE, Phase.HUNTER_PENDING)
    if not G.timer_paused:
        raise IntentError("NOT_PAUSED", "Timer is not paused.")
    G = G.model_copy(deep=True)
    remaining = G.timer_remaining_seconds or 0
    deadline = datetime.now(_UTC) + timedelta(seconds=remaining)
    G.timer_ends_at = deadline.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    G.timer_paused = False
    G.timer_remaining_seconds = None
    from api.game_queue import get_or_create_queue
    queue = get_or_create_queue(G.game_id)
    await _maybe_start_timer(G, G.game_id, queue)
    return G


async def handle_extend_timer(G, intent, redis_client, cm) -> MasterGameState:
    """Host extends the current phase by EXTEND_INCREMENT seconds."""
    _require_host(G, intent.get("player_id", ""))
    _require_phase(G, Phase.NIGHT, Phase.ROLE_DEAL, Phase.DAY, Phase.DAY_VOTE, Phase.HUNTER_PENDING)
    G = G.model_copy(deep=True)
    if G.timer_paused:
        G.timer_remaining_seconds = (G.timer_remaining_seconds or 0) + EXTEND_INCREMENT
    else:
        base = (
            datetime.fromisoformat(G.timer_ends_at.replace("Z", "+00:00"))
            if G.timer_ends_at else datetime.now(_UTC)
        )
        new_deadline = base + timedelta(seconds=EXTEND_INCREMENT)
        G.timer_ends_at = new_deadline.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        cancel_phase_timer(G.game_id)
        from api.game_queue import get_or_create_queue
        queue = get_or_create_queue(G.game_id)
        await _maybe_start_timer(G, G.game_id, queue)
    return G


async def handle_force_next(G, intent, redis_client, cm) -> MasterGameState:
    """Host immediately ends the current phase (same effect as timer expiry)."""
    _require_host(G, intent.get("player_id", ""))
    if G.phase == Phase.DAY:
        raise IntentError("USE_ADVANCE_PHASE", "Use advance_phase to move from DAY to DAY_VOTE.")
    _require_phase(G, Phase.NIGHT, Phase.ROLE_DEAL, Phase.DAY_VOTE, Phase.HUNTER_PENDING)
    cancel_phase_timer(G.game_id)
    G = G.model_copy(deep=True)
    G.timer_paused = False
    G.timer_remaining_seconds = None
    synthetic = {"type": "phase_timeout", "phase": G.phase}
    return await handle_phase_timeout(G, synthetic, redis_client, cm)


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
        # No explicit roster broadcast here — the game queue broadcasts the full
        # state (sync/update) after this handler returns, which carries the updated
        # is_connected flag to all clients including the Display.
    return G


async def handle_player_connected(G, intent, redis_client, cm) -> MasterGameState:
    """Mark a player connected after their WebSocket auth succeeds."""
    player_id = intent.get("player_id")
    if player_id and player_id in G.players:
        G = G.model_copy(deep=True)
        G.players[player_id].is_connected = True
        # No explicit roster broadcast — the queue broadcasts updated state after return.
    return G


# ── Grid system handlers ──────────────────────────────────────────────────────

async def handle_select_grid_node(G, intent, redis_client, cm) -> MasterGameState:
    """
    Villager taps a grid node to begin solving its puzzle.
    Guards: NIGHT phase, alive, wakeOrder==0, no active grid_puzzle_state, valid coords,
            node not already completed.
    """
    _require_phase(G, Phase.NIGHT)
    player_id = intent.get("player_id", "")
    player = _require_alive(G, player_id)

    role_def = ROLE_REGISTRY.get(player.role or "", {})
    if role_def.get("wakeOrder", 0) != 0:
        raise IntentError("NOT_YOUR_TURN", "Only wakeOrder==0 players can use the grid.")

    row = intent.get("row")
    col = intent.get("col")
    if not isinstance(row, int) or not isinstance(col, int) or not (0 <= row <= 4) or not (0 <= col <= 4):
        raise IntentError("INVALID_GRID_COORDS", "row and col must be integers in [0, 4].")

    G = G.model_copy(deep=True)
    player = G.players[player_id]

    if player.grid_puzzle_state and player.grid_puzzle_state.active:
        raise IntentError("PUZZLE_ALREADY_ACTIVE", "Complete or abandon your current grid puzzle first.")

    # Check node not already completed by any player
    completed_nodes = {(e["row"], e["col"]) for e in G.night_actions.grid_activity}
    if (row, col) in completed_nodes:
        raise IntentError("NODE_OCCUPIED", "This node has already been completed.")

    grid_layout = G.night_actions.grid_layout
    if grid_layout is None:
        raise IntentError("GRID_NOT_READY", "Grid layout not generated yet.")

    tier = grid_layout[row][col]

    import random
    rng = random.Random(f"{G.seed}:{G.round}:{player_id}:{row}:{col}:grid_puzzle")
    from engine.puzzle_bank import generate_grid_puzzle
    player.grid_puzzle_state = generate_grid_puzzle(tier, rng)
    player.grid_node_row = row
    player.grid_node_col = col

    # Track intent count for action_log hint
    G.night_actions.night_action_change_count[player_id] = (
        G.night_actions.night_action_change_count.get(player_id, 0) + 1
    )

    G.state_id += 1
    return G


async def handle_submit_grid_answer(G, intent, redis_client, cm) -> MasterGameState:
    """
    Villager submits their answer for the active grid node puzzle.
    On correct: generates tier hint, records activity, fires grid_ripple to wolves.
    On wrong: clears puzzle so player can try another node.
    """
    _require_phase(G, Phase.NIGHT)
    player_id = intent.get("player_id", "")
    player = _require_alive(G, player_id)

    if player.grid_puzzle_state is None or not player.grid_puzzle_state.active:
        raise IntentError("NO_ACTIVE_PUZZLE", "No active grid puzzle to answer.")

    G = G.model_copy(deep=True)
    player = G.players[player_id]
    gps = player.grid_puzzle_state
    row = player.grid_node_row
    col = player.grid_node_col

    answer_index = intent.get("answer_index")
    answer_indices = intent.get("answer_indices")  # hard_logic: [q1_idx, q2_idx]
    answer_sequence = intent.get("answer_sequence")

    # Validate answer
    if gps.puzzle_type == "hard_logic":
        q1_ci = gps.puzzle_data.get("q1", {}).get("correct_index")
        q2_ci = gps.puzzle_data.get("q2", {}).get("correct_index")
        correct = (
            isinstance(answer_indices, list)
            and len(answer_indices) == 2
            and answer_indices[0] == q1_ci
            and answer_indices[1] == q2_ci
        )
    elif gps.puzzle_type == "sequence":
        correct = answer_sequence == gps.puzzle_data.get("sequence")
    else:
        correct = isinstance(answer_index, int) and answer_index == gps.puzzle_data.get("correct_index")

    if correct and row is not None and col is not None:
        from engine.puzzle_bank import node_to_quadrant
        quadrant = node_to_quadrant(row, col)
        tier = (G.night_actions.grid_layout or [[1] * 5] * 5)[row][col]

        gps.active = False
        gps.solved = True
        gps.hint_pending = True

        # Mark last-known quadrant so wolf radar can target player after puzzle completes
        player.grid_last_quadrant = quadrant

        # Record anonymized activity for wolf radar
        sequence_idx = len(G.night_actions.grid_activity)
        G.night_actions.grid_activity.append({
            "row": row,
            "col": col,
            "quadrant": quadrant,
            "sequence_idx": sequence_idx,
        })

        # Clear position (player can navigate to another node)
        player.grid_node_row = None
        player.grid_node_col = None

        # Deliver hint to player
        from engine.hint_bank import generate_grid_hint
        hint = generate_grid_hint(G, player_id, tier, row, col)
        gps.hint_pending = False
        await cm.unicast(G.game_id, player_id, hint)

        # Fire grid_ripple side-channel to all wolves (radar animation)
        ripple = {"type": "grid_ripple", "quadrant": quadrant, "tier": tier}
        wolf_pids = [
            pid for pid, p in G.players.items()
            if p.is_alive and p.team == "werewolf"
        ]
        for wolf_pid in wolf_pids:
            await cm.unicast(G.game_id, wolf_pid, ripple)

    else:
        # Wrong answer: clear puzzle, player can try another node
        gps.active = False
        gps.solved = False
        player.grid_node_row = None
        player.grid_node_col = None

    G.state_id += 1
    return G


_MAX_SONAR_PINGS_PER_NIGHT = 4  # one per quadrant — whole pack shares this budget


async def handle_sonar_ping(G, intent, redis_client, cm) -> MasterGameState:
    """
    Wolf fires a Sonar Ping at a quadrant to get activity heat and tier breakdown.
    The pack shares a budget of MAX_SONAR_PINGS_PER_NIGHT (4) pings per night —
    one per quadrant. Wolves must allocate them wisely.
    """
    _require_phase(G, Phase.NIGHT)
    player_id = intent.get("player_id", "")
    player = _require_alive(G, player_id)

    if player.team != "werewolf":
        raise IntentError("NOT_WOLF", "Only wolf-team players can fire Sonar Pings.")

    if G.night_actions.sonar_pings_used >= _MAX_SONAR_PINGS_PER_NIGHT:
        raise IntentError(
            "SONAR_PING_LIMIT_REACHED",
            f"The pack has used all {_MAX_SONAR_PINGS_PER_NIGHT} Sonar Pings for this night.",
        )

    valid_quadrants = {"top_left", "top_right", "bottom_left", "bottom_right"}
    quadrant = intent.get("quadrant", "")
    if quadrant not in valid_quadrants:
        raise IntentError("INVALID_QUADRANT", f"quadrant must be one of {sorted(valid_quadrants)}.")

    G = G.model_copy(deep=True)

    # Compute heat and tier breakdown for the selected quadrant
    tier_counts: dict[str, int] = {"1": 0, "2": 0, "3": 0}
    heat = 0
    grid_layout = G.night_actions.grid_layout or [[1] * 5] * 5
    for entry in G.night_actions.grid_activity:
        if entry.get("quadrant") == quadrant:
            heat += 1
            node_tier = str(grid_layout[entry["row"]][entry["col"]])
            if node_tier in tier_counts:
                tier_counts[node_tier] += 1

    G.night_actions.sonar_ping_results.append({
        "quadrant": quadrant,
        "heat": heat,
        "tier_counts": tier_counts,
    })
    G.night_actions.sonar_pings_used += 1

    # Track intent count
    G.night_actions.night_action_change_count[player_id] = (
        G.night_actions.night_action_change_count.get(player_id, 0) + 1
    )

    G.state_id += 1
    return G


# ── Wolf charge / Villager defend mechanics ───────────────────────────────────

_CHARGE_THRESHOLD_MS = 5000   # pack's combined accumulated ms to auto-fire (PRD-015 §2.1)
_VALID_QUADRANTS = {"top_left", "top_right", "bottom_left", "bottom_right"}


def _players_in_quadrant(G, quadrant: str) -> list[str]:
    """Return pids of alive non-wolf players in `quadrant`.

    Primary: player has an active grid node there (mid-puzzle).
    Fallback: player's last correctly-solved node was in that quadrant (remains
    vulnerable after completing a puzzle until they solve one elsewhere).
    """
    from engine.puzzle_bank import node_to_quadrant
    result = []
    for pid, p in G.players.items():
        if not p.is_alive or p.team == "werewolf":
            continue
        if p.grid_node_row is not None and p.grid_node_col is not None:
            if node_to_quadrant(p.grid_node_row, p.grid_node_col) == quadrant:
                result.append(pid)
        elif p.grid_last_quadrant == quadrant:
            result.append(pid)
    return result


def _pack_charge_total(G, quadrant: str) -> int:
    """Sum accumulated ms across all alive wolves for `quadrant`."""
    return sum(
        G.night_actions.wolf_charges.get(pid, {}).get(quadrant, 0)
        for pid, p in G.players.items()
        if p.is_alive and p.team == "werewolf"
    )


def _apply_charge_fire(G: MasterGameState, quadrant: str) -> MasterGameState:
    """
    Pack charge threshold reached for `quadrant`.
    - Records the first active solver as charge_kill_target_id (processed by resolve_night).
    - Disrupts all active solvers in the quadrant (puzzle abandoned immediately).
    - Resets ALL wolves' accumulated charges for this quadrant to 0.
    """
    hits = _players_in_quadrant(G, quadrant)

    # Record the kill target for resolve_night (only if no prior charge kill pending)
    if hits and G.night_actions.charge_kill_target_id is None:
        G.night_actions.charge_kill_target_id = hits[0]

    # Immediately disrupt all active solvers' puzzles
    for pid in hits:
        p = G.players[pid]
        if p.grid_puzzle_state:
            p.grid_puzzle_state.active = False
            p.grid_puzzle_state.solved = False
        p.grid_node_row = None
        p.grid_node_col = None
        p.under_attack = False

    # Reset ALL wolves' charges for this quadrant (charge spent)
    for wolf_pid in list(G.night_actions.wolf_charges):
        G.night_actions.wolf_charges[wolf_pid][quadrant] = 0

    return G


async def handle_wolf_charge_update(G, intent, redis_client, cm) -> MasterGameState:
    """
    Wolf reports current charge state for a quadrant.

    is_active=True  → wolf is actively holding; set under_attack on villagers in that quadrant.
    is_active=False → wolf released (pause); charge is preserved but under_attack clears.
    accumulated_ms  → this wolf's cumulative hold time (persisted server-side per wolf).

    After recording, the server checks the PACK POOL (sum of all wolves' accumulated ms for
    this quadrant). If the pool reaches CHARGE_THRESHOLD_MS (5000 ms), the charge auto-fires:
    - charge_kill_target_id is set (used by resolve_night at night end)
    - Active solvers' puzzles are disrupted immediately
    - All wolves' charges for this quadrant reset to 0

    Cooperation mechanic: 2 wolves each holding ~2.5 s fires together. First quadrant to
    reach the threshold wins; second quadrant fire is still a disruption but does not add
    another kill (charge_kill_target_id already set).
    """
    _require_phase(G, Phase.NIGHT)
    player_id = intent.get("player_id", "")
    player = _require_alive(G, player_id)

    if player.team != "werewolf":
        raise IntentError("NOT_WOLF", "Only wolf-team players can charge a quadrant.")

    if player_id == G.night_actions.roleblocked_player_id:
        raise IntentError("ROLEBLOCKED", "Your night action is blocked.")

    quadrant = intent.get("quadrant", "")
    if quadrant not in _VALID_QUADRANTS:
        raise IntentError("INVALID_QUADRANT", f"quadrant must be one of {sorted(_VALID_QUADRANTS)}.")

    accumulated_ms = intent.get("accumulated_ms", 0)
    if not isinstance(accumulated_ms, (int, float)) or accumulated_ms < 0:
        raise IntentError("INVALID_CHARGE", "accumulated_ms must be a non-negative number.")
    accumulated_ms = min(int(accumulated_ms), _CHARGE_THRESHOLD_MS)

    is_active = bool(intent.get("is_active", False))

    G = G.model_copy(deep=True)

    # Persist this wolf's accumulated charge for the quadrant
    if player_id not in G.night_actions.wolf_charges:
        G.night_actions.wolf_charges[player_id] = {}
    G.night_actions.wolf_charges[player_id][quadrant] = accumulated_ms

    # Set or clear under_attack on villagers currently solving in this quadrant
    for pid in _players_in_quadrant(G, quadrant):
        G.players[pid].under_attack = is_active

    # ── Auto-fire check: does the pack pool now exceed the threshold? ─────────
    if _pack_charge_total(G, quadrant) >= _CHARGE_THRESHOLD_MS:
        G = _apply_charge_fire(G, quadrant)

    G.state_id += 1
    return G


async def handle_grid_defend(G, intent, redis_client, cm) -> MasterGameState:
    """
    Villager presses Defend while under attack.
    Clears under_attack for this player AND resets ALL wolves' charges for this
    player's quadrant to 0 — the entire pack must restart from zero.
    """
    _require_phase(G, Phase.NIGHT)
    player_id = intent.get("player_id", "")
    player = _require_alive(G, player_id)

    if player.team == "werewolf":
        raise IntentError("INVALID_ACTION", "Wolves cannot use the Defend action.")

    if not player.under_attack:
        raise IntentError("NOT_UNDER_ATTACK", "No active charge to defend against.")

    G = G.model_copy(deep=True)
    p = G.players[player_id]

    # Clear attack state on this player
    p.under_attack = False

    # Reset ALL wolves' charges for this player's quadrant (pack's effort is broken)
    if p.grid_node_row is not None and p.grid_node_col is not None:
        from engine.puzzle_bank import node_to_quadrant
        target_q = node_to_quadrant(p.grid_node_row, p.grid_node_col)
        for wolf_pid in list(G.night_actions.wolf_charges):
            G.night_actions.wolf_charges[wolf_pid][target_q] = 0

    G.state_id += 1
    return G
