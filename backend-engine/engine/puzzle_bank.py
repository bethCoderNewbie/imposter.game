"""
Archive puzzle bank: parses puzzles.md and generates night puzzles + hint payloads.
All generation is deterministic given the game seed — no I/O after module load.

puzzles.md format:  **Q:** <question> **A:** <answer>
BANK holds 400 (question, answer) tuples loaded at import time.
"""
from __future__ import annotations

import pathlib
import random
import re
import secrets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.state.models import MasterGameState, PuzzleState

# ── Static bank ──────────────────────────────────────────────────────────────

_PUZZLES_MD = pathlib.Path(__file__).parent.parent.parent / "puzzles.md"
BANK: list[tuple[str, str]] = re.findall(
    r"\*\*Q:\*\* (.+?) \*\*A:\*\* (.+)",
    _PUZZLES_MD.read_text(encoding="utf-8"),
)

_SEQUENCE_COLORS = ["red", "blue", "green", "yellow"]

# Roles whose absence/presence yields a high-value hint
_HIGH_IMPACT_ABSENT_ROLES = ["alpha_wolf", "framer", "infector", "serial_killer", "arsonist"]
# Guaranteed baseline roles — not worth hinting about presence
_BASELINE_ROLES = {"villager", "werewolf", "seer"}


# ── Puzzle generation ─────────────────────────────────────────────────────────

def generate_night_puzzle(G: "MasterGameState") -> "PuzzleState":
    """
    Select and generate a PuzzleState for the current night round.
    Seeded by (game seed : round) — deterministic, no side effects.
    Weights: 50% logic, 25% math, 25% sequence.
    """
    rng = random.Random(f"{G.seed}:{G.round}:puzzle")
    puzzle_type = rng.choices(
        ["logic", "math", "sequence"],
        weights=[50, 25, 25],
        k=1,
    )[0]

    if puzzle_type == "logic":
        return _make_logic_puzzle(rng)
    if puzzle_type == "math":
        return _make_math_puzzle(rng, G.round)
    return _make_sequence_puzzle(rng)


def _make_logic_puzzle(rng: random.Random) -> "PuzzleState":
    from engine.state.models import PuzzleState

    # Pick question and a distractor from a different entry
    q_idx = rng.randrange(len(BANK))
    d_idx = rng.randrange(len(BANK))
    while d_idx == q_idx:
        d_idx = rng.randrange(len(BANK))

    question, correct_answer = BANK[q_idx]
    _, distractor = BANK[d_idx]

    options = [correct_answer, distractor]
    rng.shuffle(options)
    correct_index = options.index(correct_answer)

    return PuzzleState(
        puzzle_type="logic",
        puzzle_data={
            "question": question,
            "answer_options": options,
            "correct_index": correct_index,
        },
        time_limit_seconds=20,
    )


def _make_math_puzzle(rng: random.Random, round_number: int) -> "PuzzleState":
    from engine.state.models import PuzzleState

    if round_number <= 2:
        # Single operation
        op = rng.choice(["+", "-", "×"])
        if op == "×":
            a = rng.randint(2, 9)
            b = rng.randint(2, 9)
            correct = a * b
        elif op == "+":
            a = rng.randint(2, 20)
            b = rng.randint(2, 20)
            correct = a + b
        else:
            a = rng.randint(5, 25)
            b = rng.randint(2, a)
            correct = a - b
        expression = f"{a} {op} {b} = ?"
    else:
        # Two-step: (a op1 b) op2 c
        op1 = rng.choice(["+", "-", "×"])
        op2 = rng.choice(["+", "-"])
        if op1 == "×":
            a = rng.randint(2, 9)
            b = rng.randint(2, 6)
            mid = a * b
        elif op1 == "+":
            a = rng.randint(2, 15)
            b = rng.randint(2, 15)
            mid = a + b
        else:
            a = rng.randint(10, 25)
            b = rng.randint(2, a)
            mid = a - b
        c = rng.randint(2, 8)
        correct = mid + c if op2 == "+" else mid - c
        expression = f"{a} {op1} {b} {op2} {c} = ?"

    # 2 distinct wrong answers near the correct value
    offsets = [o for o in range(-6, 7) if o != 0]
    rng.shuffle(offsets)
    wrongs: list[int] = []
    for off in offsets:
        cand = correct + off
        if cand not in wrongs and cand != correct and cand >= 0:
            wrongs.append(cand)
        if len(wrongs) == 2:
            break

    options_str = [str(correct), str(wrongs[0]), str(wrongs[1])]
    rng.shuffle(options_str)
    correct_index = options_str.index(str(correct))

    return PuzzleState(
        puzzle_type="math",
        puzzle_data={
            "expression": expression,
            "answer_options": options_str,
            "correct_index": correct_index,
        },
        time_limit_seconds=15,
    )


def _make_sequence_puzzle(rng: random.Random) -> "PuzzleState":
    from engine.state.models import PuzzleState

    sequence = [rng.choice(_SEQUENCE_COLORS) for _ in range(4)]
    return PuzzleState(
        puzzle_type="sequence",
        puzzle_data={"sequence": sequence},
        time_limit_seconds=30,
    )


# ── Hint generation ───────────────────────────────────────────────────────────

def generate_hint(G: "MasterGameState", player_id: str) -> dict:
    """
    Generate a real HintPayload for a player who solved their Archive puzzle.
    Seeded by (game seed : round : player_id) so simultaneous solvers can get
    different hints even in the same round.
    Hint categories: wolf_count (always), no_role_present (if applicable),
    role_present (if applicable), neutral_exists (if applicable).
    seer_blocked_last_night is omitted — roleblocked_player_id is not set until
    night resolution runs, which happens after puzzle delivery.
    """
    rng = random.Random(f"{G.seed}:{G.round}:{player_id}:hint")

    composition: dict[str, int] = {}
    for player in G.players.values():
        if player.role:
            composition[player.role] = composition.get(player.role, 0) + 1

    pool: list[dict] = []

    # wolf_count — always available
    wolf_count = sum(1 for p in G.players.values() if p.team == "werewolf")
    plural = wolf_count != 1
    pool.append({
        "category": "wolf_count",
        "text": (
            f"There {'are' if plural else 'is'} {wolf_count} "
            f"{'Wolves' if plural else 'Wolf'} total in this game."
        ),
        "expires_after_round": None,
    })

    # no_role_present — pick one absent high-impact role
    absent = [r for r in _HIGH_IMPACT_ABSENT_ROLES if r not in composition]
    if absent:
        role_name = rng.choice(absent)
        pool.append({
            "category": "no_role_present",
            "text": f"There is NO {role_name.replace('_', ' ').title()} in this game.",
            "expires_after_round": None,
        })

    # role_present — pick one present non-baseline role
    present_special = [r for r in composition if r not in _BASELINE_ROLES]
    if present_special:
        role_name = rng.choice(present_special)
        pool.append({
            "category": "role_present",
            "text": f"There IS a {role_name.replace('_', ' ').title()} in this game.",
            "expires_after_round": None,
        })

    # neutral_exists — only if a living neutral player exists
    if any(p.is_alive and p.team == "neutral" for p in G.players.values()):
        pool.append({
            "category": "neutral_exists",
            "text": "At least one Neutral player is alive in this game.",
            "expires_after_round": G.round + 1,
        })

    chosen = rng.choice(pool)
    return {
        "type": "hint_reward",
        "hint_id": secrets.token_urlsafe(12),
        "category": chosen["category"],
        "text": chosen["text"],
        "round": G.round,
        "expires_after_round": chosen["expires_after_round"],
    }
