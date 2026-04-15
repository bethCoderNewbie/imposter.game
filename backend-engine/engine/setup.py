"""
Game initialization: composition building, role assignment, and MasterGameState creation.
All functions are pure — no I/O.
"""

from __future__ import annotations

import random
import secrets
import uuid
from copy import deepcopy
from typing import Any

from engine.roles_loader import (
    BALANCE_WEIGHT_SYSTEM,
    CLIENT_SAFE_ROLE_REGISTRY,
    DYNAMIC_TEMPLATES,
    ROLE_REGISTRY,
    WAKE_ORDER,
)
from engine.state.enums import Phase, Team
from engine.state.models import GameConfig, MasterGameState, NightActions, PlayerState

DIFFICULTY_BALANCE_RANGE: dict[str, list[int]] = {
    "easy":     [0,  4],
    "standard": [-2, 2],
    "hard":     [-4, 0],
}

# Neutral roles injected on hard difficulty (jester excluded — village can exploit its win condition)
_HARD_NEUTRAL_ROLES = ["serial_killer", "arsonist"]


def _inject_hard_neutrals(
    result: dict[str, int],
    player_count: int,
    rng: random.Random,
) -> dict[str, int]:
    """
    Post-process composition for hard difficulty.
    Guarantees ≥1 neutral (serial_killer/arsonist) for all hard games (5+),
    ≥2 for 13+ players. Swaps villager slots to make room.
    """
    target = 2 if player_count >= 13 else 1
    current = sum(result.get(r, 0) for r in _HARD_NEUTRAL_ROLES)
    needed = target - current

    for _ in range(needed):
        if result.get("villager", 0) > 0:
            neutral = rng.choice(_HARD_NEUTRAL_ROLES)
            result["villager"] -= 1
            if result["villager"] == 0:
                del result["villager"]
            result[neutral] = result.get(neutral, 0) + 1

    return result


def _find_template(player_count: int) -> dict[str, Any]:
    """Return the dynamic template matching the given player count."""
    for tpl in DYNAMIC_TEMPLATES.values():
        if not isinstance(tpl, dict):
            continue
        pc = tpl.get("playerCount", {})
        if isinstance(pc, dict) and pc.get("min", 0) <= player_count <= pc.get("max", 0):
            return tpl
    raise ValueError(f"No dynamic template found for {player_count} players (valid: 5–18)")


def _balance_weight(composition: dict[str, int]) -> int:
    return sum(
        ROLE_REGISTRY[role_id]["balanceWeight"] * count
        for role_id, count in composition.items()
        if role_id in ROLE_REGISTRY
    )


def build_composition(
    player_count: int,
    seed: str | None = None,
    target_range: list[int] | None = None,
    difficulty_level: str | None = None,
) -> dict[str, int]:
    """
    Select roles for a game using the dynamic template system.
    Returns {role_id: count} summing to player_count.
    """
    if player_count < 5 or player_count > 18:
        raise ValueError(f"player_count must be 5–18, got {player_count}")

    rng = random.Random(seed)
    template = _find_template(player_count)
    composition: dict[str, int] = {}
    slots_filled = 0

    # Step 1: fill guaranteed roles
    for role_id, count in template.get("guaranteed", {}).items():
        composition[role_id] = composition.get(role_id, 0) + count
        slots_filled += count

    # Step 2: fill flex pools
    effective_range: list[int] = target_range or BALANCE_WEIGHT_SYSTEM.get("targetRange", [-2, 2])

    def _draw_from_pool(pool: dict[str, Any], rng: random.Random) -> list[str]:
        picks = pool["picks"]
        options = pool["options"]
        if picks == "remaining_slots":
            picks = player_count - slots_filled - sum(
                _count_pool_picks(p) for p in template["flexPools"][template["flexPools"].index(pool) + 1:]
            )
            picks = max(0, picks)
        results = []
        for _ in range(picks):
            choice = rng.choice(options)
            if choice != "none":
                results.append(choice)
        return results

    def _count_pool_picks(pool: dict[str, Any]) -> int:
        picks = pool["picks"]
        if picks == "remaining_slots":
            return 0
        return picks

    def _fill_pools(rng: random.Random) -> dict[str, int]:
        comp = deepcopy(composition)
        filled = slots_filled
        for pool in template["flexPools"]:
            picks_val = pool["picks"]
            options = pool["options"]
            if picks_val == "remaining_slots":
                n = player_count - filled
            else:
                n = picks_val
            for _ in range(n):
                choice = rng.choice(options)
                if choice != "none":
                    comp[choice] = comp.get(choice, 0) + 1
                filled += 1
        return comp

    # First pass
    result = _fill_pools(rng)

    # One re-roll pass if balance outside target range
    weight = _balance_weight(result)
    if not (effective_range[0] <= weight <= effective_range[1]):
        reroll_rng = random.Random(seed + "_reroll" if seed else None)
        result2 = _fill_pools(reroll_rng)
        weight2 = _balance_weight(result2)
        # Accept reroll if it's closer to balance, regardless of range
        if abs(weight2) < abs(weight):
            result = result2

    # Hard difficulty: guarantee neutral chaos roles
    if difficulty_level == "hard":
        result = _inject_hard_neutrals(result, player_count, rng)

    # Validate sum
    total = sum(result.values())
    if total != player_count:
        # Adjust by adding/removing villagers as a fallback
        diff = player_count - total
        result["villager"] = max(0, result.get("villager", 0) + diff)

    return result


def assign_roles(player_ids: list[str], composition: dict[str, int], seed: str) -> dict[str, str]:
    """
    Shuffle player IDs and map each to a role using the composition.
    Returns {player_id: role_id}. Deterministic for the same seed.
    """
    rng = random.Random(seed + "_assign")
    shuffled = list(player_ids)
    rng.shuffle(shuffled)

    role_pool: list[str] = []
    for role_id, count in composition.items():
        role_pool.extend([role_id] * count)

    if len(role_pool) != len(shuffled):
        raise ValueError(
            f"Composition total ({len(role_pool)}) != player count ({len(shuffled)})"
        )

    return {pid: role for pid, role in zip(shuffled, role_pool)}


def setup_game(
    game_id: str,
    host_player_id: str | None = None,
    config: GameConfig | dict | None = None,
    joined_players: dict[str, PlayerState] | None = None,
    host_secret: str | None = None,
) -> MasterGameState:
    """
    Create a fully initialized MasterGameState ready for the lobby phase.
    Pure function — no I/O.
    config may be a GameConfig, a plain dict (for tests), or None — all produce a default lobby config.
    """
    initial_player_count = 1 if host_player_id else 0
    if not isinstance(config, GameConfig):
        from engine.config import get_settings
        s = get_settings()
        config = GameConfig(
            player_count=initial_player_count,
            roles={},
            night_timer_seconds=s.night_timer_seconds,
            day_timer_seconds=s.day_timer_seconds,
            vote_timer_seconds=s.vote_timer_seconds,
            role_deal_timer_seconds=s.role_deal_timer_seconds,
            hunter_pending_timer_seconds=s.hunter_pending_timer_seconds,
        )
    seed = secrets.token_hex(16)

    players: dict[str, PlayerState] = dict(joined_players) if joined_players else {}

    # Ensure host player exists in the lobby (only when host_player_id provided)
    if host_player_id and host_player_id not in players:
        players[host_player_id] = PlayerState(
            player_id=host_player_id,
            display_name="Host",
        )

    # If players are already joined (from lobby), assign roles now
    if players and config.player_count >= 5 and len(players) == config.player_count:
        composition = build_composition(config.player_count, seed)
        role_map = assign_roles(list(players.keys()), composition, seed)
        for pid, role_id in role_map.items():
            role_def = ROLE_REGISTRY[role_id]
            players[pid].role = role_id
            players[pid].team = role_def["team"]
    elif not config.roles and config.player_count >= 5:
        # Build composition eagerly so it's stored in config (only when player_count is valid)
        composition = build_composition(config.player_count, seed)
        config = config.model_copy(update={"roles": composition})

    return MasterGameState(
        game_id=game_id,
        seed=seed,
        phase=Phase.LOBBY,
        round=0,
        host_player_id=host_player_id,
        host_secret=host_secret,
        config=config,
        players=players,
        night_actions=NightActions(actions_required_count=0, actions_submitted_count=0),
        role_registry=CLIENT_SAFE_ROLE_REGISTRY,
        state_id=0,
    )
