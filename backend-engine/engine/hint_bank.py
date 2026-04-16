"""
Hint bank: generates HintPayload dicts for Archive puzzle solves and grid node solves.
All generation is deterministic given the game seed — no I/O after module load.

Archive hints (generate_hint):   Tier 1 categories. Called on Archive puzzle solve.
Grid hints (generate_grid_hint): Tier 1/2/3 based on node tier. Called on grid node solve.

Tier 1 (green nodes, 5s):  Composition + recap hints (same pool as Archive).
Tier 2 (yellow nodes, 10s): Relational logic (alignment links, player groups).
Tier 3 (red node, 20s):    Specific intel (innocent clears, action logs).
"""
from __future__ import annotations

import random
import secrets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.state.models import MasterGameState

# Roles whose absence/presence yields a high-value hint
_HIGH_IMPACT_ABSENT_ROLES = ["alpha_wolf", "framer", "infector", "serial_killer", "arsonist"]
# Guaranteed baseline roles — not worth hinting about presence
_BASELINE_ROLES = {"villager", "werewolf", "seer"}
# Elimination causes that indicate a non-wolf kill (for non_wolf_kill hint category)
_NON_WOLF_CAUSES = {"arsonist_ignite", "serial_killer_kill", "broken_heart", "hunter_revenge"}
# Round threshold: rounds < this are vague, rounds >= this are specific
_VAGUE_ROUND_THRESHOLD = 3


# ── Archive hint generation ───────────────────────────────────────────────────

def generate_hint(G: "MasterGameState", player_id: str) -> dict:
    """
    Generate a HintPayload for a player who solved their Archive puzzle.
    Seeded by (game seed : round : player_id) so simultaneous solvers get
    different hints even in the same round.

    Rounds 1–2 (< _VAGUE_ROUND_THRESHOLD): composition hints are vague.
    Round 3+: hints are specific.

    Categories: wolf_count (always), no_role_present, role_present, neutral_exists,
    non_wolf_kill (round 2+), lovers_exist (if Cupid linked a pair).
    """
    rng = random.Random(f"{G.seed}:{G.round}:{player_id}:hint")
    pool = _build_tier1_pool(G, rng)
    chosen = rng.choice(pool)
    return {**_wrap_hint(chosen, G.round), "source": "archive"}


# ── Grid hint generation ──────────────────────────────────────────────────────

def generate_grid_hint(
    G: "MasterGameState",
    player_id: str,
    tier: int,
    row: int,
    col: int,
) -> dict:
    """
    Generate a tiered HintPayload for a player who solved a grid node.
    Seeded by (seed : round : player_id : row : col) — deterministic per node per player.

    tier 1 → Tier 1 pool (same as Archive, plus new composition categories)
    tier 2 → Tier 2 pool (relational logic)
    tier 3 → Tier 3 pool (specific intel)
    """
    rng = random.Random(f"{G.seed}:{G.round}:{player_id}:{row}:{col}:grid_hint")

    if tier == 1:
        pool = _build_tier1_pool(G, rng)
    elif tier == 2:
        pool = _build_tier2_pool(G, rng)
    else:
        pool = _build_tier3_pool(G, rng)

    # Fallback to Tier 1 if higher tier pool is empty (edge case: game almost over)
    if not pool:
        pool = _build_tier1_pool(G, rng)

    chosen = rng.choice(pool)
    return {**_wrap_hint(chosen, G.round), "source": "grid"}


# ── Tier pool builders ────────────────────────────────────────────────────────

def _build_tier1_pool(G: "MasterGameState", rng: random.Random) -> list[dict]:
    """Tier 1: composition + recap hints (Archive categories + new ones)."""
    is_vague = G.round < _VAGUE_ROUND_THRESHOLD
    pool: list[dict] = []

    composition: dict[str, int] = {}
    for player in G.players.values():
        if player.role:
            composition[player.role] = composition.get(player.role, 0) + 1

    # wolf_count — always available
    wolf_count = sum(1 for p in G.players.values() if p.team == "werewolf")
    if is_vague:
        low = max(1, wolf_count - 1)
        high = wolf_count + 1
        wolf_text = f"The Archives suggest between {low} and {high} Wolves are present in this game."
    else:
        plural = wolf_count != 1
        wolf_text = (
            f"There {'are' if plural else 'is'} {wolf_count} "
            f"{'Wolves' if plural else 'Wolf'} total in this game."
        )
    pool.append({"category": "wolf_count", "text": wolf_text, "expires_after_round": None})

    # no_role_present
    absent = [r for r in _HIGH_IMPACT_ABSENT_ROLES if r not in composition]
    if absent:
        role_name = rng.choice(absent)
        if is_vague:
            no_role_text = "The Archives hint that a certain powerful role is absent from this game."
        else:
            no_role_text = f"There is NO {role_name.replace('_', ' ').title()} in this game."
        pool.append({"category": "no_role_present", "text": no_role_text, "expires_after_round": None})

    # role_present
    present_special = [r for r in composition if r not in _BASELINE_ROLES]
    if present_special:
        role_name = rng.choice(present_special)
        if is_vague:
            role_text = "The Archives suggest at least one special role is in play beyond the basics."
        else:
            role_text = f"There IS a {role_name.replace('_', ' ').title()} in this game."
        pool.append({"category": "role_present", "text": role_text, "expires_after_round": None})

    # neutral_exists
    if any(p.is_alive and p.team == "neutral" for p in G.players.values()):
        pool.append({
            "category": "neutral_exists",
            "text": "At least one Neutral player is alive in this game.",
            "expires_after_round": G.round + 1,
        })

    # non_wolf_kill (round 2+)
    if G.round >= 2:
        last_night_non_wolf = [
            e for e in G.elimination_log
            if e.round == G.round - 1
            and e.phase == "night"
            and e.cause in _NON_WOLF_CAUSES
        ]
        if last_night_non_wolf:
            pool.append({
                "category": "non_wolf_kill",
                "text": "The last night's death was not the wolves' doing.",
                "expires_after_round": G.round + 1,
            })

    # lovers_exist
    if G.lovers_pair:
        if is_vague:
            lovers_text = "Two souls in this village share an unbreakable bond."
        else:
            lovers_text = "Two players are bound together — if one falls, the other follows."
        pool.append({"category": "lovers_exist", "text": lovers_text, "expires_after_round": None})

    # alive_count (new Tier 1 category)
    alive_wolves = sum(1 for p in G.players.values() if p.is_alive and p.team == "werewolf")
    alive_villagers = sum(1 for p in G.players.values() if p.is_alive and p.team == "village")
    if not is_vague:
        pool.append({
            "category": "alive_count",
            "text": (
                f"There are currently {alive_wolves} "
                f"{'Wolf' if alive_wolves == 1 else 'Wolves'} and "
                f"{alive_villagers} "
                f"{'Villager' if alive_villagers == 1 else 'Villagers'} alive."
            ),
            "expires_after_round": G.round + 1,
        })

    # role_alive_check (new Tier 1 category)
    _alive_check = _make_role_alive_check(G, rng, is_vague)
    if _alive_check:
        pool.append(_alive_check)

    # night_recap — sonar pings used this night (new Tier 1 category)
    sonar_pings = getattr(G.night_actions, "sonar_pings_used", 0)
    if sonar_pings > 0:
        pool.append({
            "category": "night_recap",
            "text": (
                f"The Wolves have used {sonar_pings} Sonar "
                f"{'Ping' if sonar_pings == 1 else 'Pings'} tonight."
            ),
            "expires_after_round": G.round + 1,
        })

    return pool


def _make_role_alive_check(G: "MasterGameState", rng: random.Random, is_vague: bool) -> dict | None:
    """Generate a role_alive_check hint. Consumes RNG to preserve seed sequence."""
    # Candidate: a high-impact role that IS in the game
    all_roles = {p.role for p in G.players.values() if p.role}
    high_impact = [r for r in _HIGH_IMPACT_ABSENT_ROLES if r in all_roles]

    # Also consider medic (doctor) as a meaningful role to check
    check_roles = high_impact + (["doctor"] if "doctor" in all_roles else [])

    if not check_roles:
        rng.random()  # consume RNG to keep seed sequence stable
        return None

    role_name = rng.choice(check_roles)
    role_alive = any(p.is_alive and p.role == role_name for p in G.players.values())

    if is_vague:
        return None  # role_alive_check is always specific (reveals role name)

    display = role_name.replace("_", " ").title()
    if role_alive:
        text = f"The {display} is still alive."
    else:
        text = f"The {display} has been eliminated."

    return {
        "category": "role_alive_check",
        "text": text,
        "expires_after_round": G.round + 1,
    }


def _build_tier2_pool(G: "MasterGameState", rng: random.Random) -> list[dict]:
    """Tier 2: relational logic hints."""
    pool: list[dict] = []
    alive = [pid for pid, p in G.players.items() if p.is_alive]
    alive_wolves = [pid for pid in alive if G.players[pid].team == "werewolf"]
    alive_non_wolves = [pid for pid in alive if G.players[pid].team != "werewolf"]

    # one_of_three: pick 1 wolf + 2 non-wolves
    if alive_wolves and len(alive_non_wolves) >= 2:
        wolf_pick = rng.choice(alive_wolves)
        decoys = rng.sample(alive_non_wolves, 2)
        group = [wolf_pick] + decoys
        rng.shuffle(group)
        names = [G.players[pid].display_name for pid in group]
        pool.append({
            "category": "one_of_three",
            "text": f"At least one Wolf is among {names[0]}, {names[1]}, and {names[2]}.",
            "expires_after_round": G.round + 1,
        })

    # same_alignment: pick 2 alive players on the same team
    if len(alive) >= 2:
        # Shuffle a copy to get random pairs
        shuffled = list(alive)
        rng.shuffle(shuffled)
        same_pair = None
        for i in range(len(shuffled)):
            for j in range(i + 1, len(shuffled)):
                if G.players[shuffled[i]].team == G.players[shuffled[j]].team:
                    same_pair = (shuffled[i], shuffled[j])
                    break
            if same_pair:
                break
        if same_pair:
            n1 = G.players[same_pair[0]].display_name
            n2 = G.players[same_pair[1]].display_name
            pool.append({
                "category": "same_alignment",
                "text": f"{n1} and {n2} share the same alignment.",
                "expires_after_round": G.round + 1,
            })

    # diff_alignment: pick 1 wolf + 1 non-wolf
    if alive_wolves and alive_non_wolves:
        w = rng.choice(alive_wolves)
        v = rng.choice(alive_non_wolves)
        n1, n2 = G.players[w].display_name, G.players[v].display_name
        pool.append({
            "category": "diff_alignment",
            "text": f"{n1} and {n2} are NOT on the same team.",
            "expires_after_round": G.round + 1,
        })

    # positional_clue: which quadrant has the most activity
    grid_activity = getattr(G.night_actions, "grid_activity", [])
    if grid_activity:
        quadrant_counts: dict[str, int] = {}
        for entry in grid_activity:
            q = entry.get("quadrant", "")
            if q:
                quadrant_counts[q] = quadrant_counts.get(q, 0) + 1
        if quadrant_counts:
            hottest = max(quadrant_counts, key=lambda q: quadrant_counts[q])
            display_q = hottest.replace("_", "-")
            pool.append({
                "category": "positional_clue",
                "text": f"High activity was detected in the {display_q} quadrant tonight.",
                "expires_after_round": G.round + 1,
            })

    return pool


def _build_tier3_pool(G: "MasterGameState", rng: random.Random) -> list[dict]:
    """Tier 3: specific intel hints."""
    pool: list[dict] = []
    alive = [pid for pid, p in G.players.items() if p.is_alive]
    alive_non_wolves = [pid for pid in alive if G.players[pid].team != "werewolf"]

    # innocent_clear: name one alive non-wolf
    if alive_non_wolves:
        safe_pid = rng.choice(alive_non_wolves)
        name = G.players[safe_pid].display_name
        pool.append({
            "category": "innocent_clear",
            "text": f"The Archives confirm: {name} is NOT a Wolf.",
            "expires_after_round": None,
        })

    # action_log: highest-change player (no name — let village infer)
    change_count = getattr(G.night_actions, "night_action_change_count", {})
    if change_count:
        max_count = max(change_count.values())
        if max_count >= 2:
            pool.append({
                "category": "action_log",
                "text": (
                    f"A player in this game changed their mind {max_count} times "
                    "during the night phase."
                ),
                "expires_after_round": G.round + 1,
            })

    return pool


# ── Shared helpers ────────────────────────────────────────────────────────────

def _wrap_hint(chosen: dict, round_number: int) -> dict:
    """Wrap a raw pool entry into a full HintPayload dict."""
    return {
        "type": "hint_reward",
        "hint_id": secrets.token_urlsafe(12),
        "category": chosen["category"],
        "text": chosen["text"],
        "round": round_number,
        "expires_after_round": chosen["expires_after_round"],
    }
