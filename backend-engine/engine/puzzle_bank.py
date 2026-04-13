"""
Archive puzzle bank: parses puzzles.md and generates night puzzles + hint payloads.
All generation is deterministic given the game seed — no I/O after module load.

puzzles.md format:  **Q:** <question> **A:** <answer>
BANK holds 400 (question, answer, category) tuples loaded at import time.
BANK_BY_CATEGORY maps category name → list of indices into BANK.
Logic puzzles draw 3 same-category distractors → 4-option format (ADR-012).
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

# Each entry: (question, answer, category)
_BankEntry = tuple[str, str, str]

_HEADER_RE = re.compile(r"^\s*(?:#{1,3}\s+)?\*\*([^*\d][^*]*)\*\*\s*$")
_QA_RE = re.compile(r"\*\*Q:\*\*\s+(.+?)\s+\*\*A:\*\*\s+(.+)")


def _parse_bank(text: str) -> tuple[list[_BankEntry], dict[str, list[int]]]:
    bank: list[_BankEntry] = []
    by_category: dict[str, list[int]] = {}
    current_category = "Uncategorized"
    for line in text.splitlines():
        header_match = _HEADER_RE.match(line)
        if header_match:
            current_category = header_match.group(1).strip()
            continue
        qa_match = _QA_RE.search(line)
        if qa_match:
            idx = len(bank)
            bank.append((qa_match.group(1), qa_match.group(2), current_category))
            by_category.setdefault(current_category, []).append(idx)
    return bank, by_category


BANK: list[_BankEntry]
BANK_BY_CATEGORY: dict[str, list[int]]
BANK, BANK_BY_CATEGORY = _parse_bank(_PUZZLES_MD.read_text(encoding="utf-8"))

_SEQUENCE_COLORS = ["red", "blue", "green", "yellow"]

# Roles whose absence/presence yields a high-value hint
_HIGH_IMPACT_ABSENT_ROLES = ["alpha_wolf", "framer", "infector", "serial_killer", "arsonist"]
# Guaranteed baseline roles — not worth hinting about presence
_BASELINE_ROLES = {"villager", "werewolf", "seer"}
# Elimination causes that indicate a non-wolf kill (for non_wolf_kill hint category)
_NON_WOLF_CAUSES = {"arsonist_ignite", "serial_killer_kill", "broken_heart", "hunter_revenge"}
# Round threshold: rounds < this are vague, rounds >= this are specific
_VAGUE_ROUND_THRESHOLD = 3


# ── Puzzle generation ─────────────────────────────────────────────────────────

def generate_night_puzzle(G: "MasterGameState", player_id: str) -> "PuzzleState":
    """
    Select and generate a PuzzleState for the given player in the current night round.
    Seeded by (game seed : round : player_id) — deterministic, per-player distinct puzzle.
    Weights: 50% logic, 25% math, 25% sequence.
    """
    rng = random.Random(f"{G.seed}:{G.round}:{player_id}:puzzle")
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

    # Pick question; collect 3 same-category distractors (ADR-012)
    q_idx = rng.randrange(len(BANK))
    question, correct_answer, category = BANK[q_idx]

    peers = [i for i in BANK_BY_CATEGORY.get(category, []) if i != q_idx]
    distractor_indices = rng.sample(peers, min(3, len(peers)))
    distractors = [BANK[i][1] for i in distractor_indices]

    # Fallback: pad with cross-category answers if the category had < 3 peers
    seen = {correct_answer} | set(distractors)
    while len(distractors) < 3:
        d_idx = rng.randrange(len(BANK))
        candidate = BANK[d_idx][1]
        if candidate not in seen:
            distractors.append(candidate)
            seen.add(candidate)

    options = [correct_answer] + distractors
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

    Rounds 1–2 (< _VAGUE_ROUND_THRESHOLD): composition hints are vague — direction
    without naming specifics (role names, exact counts).
    Round 3+: hints are specific (exact counts, role names).

    Categories: wolf_count (always), no_role_present, role_present, neutral_exists,
    non_wolf_kill (round 2+), lovers_exist (if Cupid linked a pair).
    seer_blocked_last_night is omitted — roleblocked_player_id is not set until
    night resolution runs, which happens after puzzle delivery.
    """
    rng = random.Random(f"{G.seed}:{G.round}:{player_id}:hint")
    is_vague = G.round < _VAGUE_ROUND_THRESHOLD

    composition: dict[str, int] = {}
    for player in G.players.values():
        if player.role:
            composition[player.role] = composition.get(player.role, 0) + 1

    pool: list[dict] = []

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

    # no_role_present — pick one absent high-impact role
    # rng.choice always called to preserve RNG sequence even when vague
    absent = [r for r in _HIGH_IMPACT_ABSENT_ROLES if r not in composition]
    if absent:
        role_name = rng.choice(absent)
        if is_vague:
            no_role_text = "The Archives hint that a certain powerful role is absent from this game."
        else:
            no_role_text = f"There is NO {role_name.replace('_', ' ').title()} in this game."
        pool.append({"category": "no_role_present", "text": no_role_text, "expires_after_round": None})

    # role_present — pick one present non-baseline role
    # rng.choice always called to preserve RNG sequence even when vague
    present_special = [r for r in composition if r not in _BASELINE_ROLES]
    if present_special:
        role_name = rng.choice(present_special)
        if is_vague:
            role_text = "The Archives suggest at least one special role is in play beyond the basics."
        else:
            role_text = f"There IS a {role_name.replace('_', ' ').title()} in this game."
        pool.append({"category": "role_present", "text": role_text, "expires_after_round": None})

    # neutral_exists — only if a living neutral player exists
    if any(p.is_alive and p.team == "neutral" for p in G.players.values()):
        pool.append({
            "category": "neutral_exists",
            "text": "At least one Neutral player is alive in this game.",
            "expires_after_round": G.round + 1,
        })

    # non_wolf_kill — behavioral, round 2+
    # Fires when last night had at least one kill not caused by wolves
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

    # lovers_exist — if Cupid linked a pair this game
    if G.lovers_pair:
        if is_vague:
            lovers_text = "Two souls in this village share an unbreakable bond."
        else:
            lovers_text = "Two players are bound together — if one falls, the other follows."
        pool.append({"category": "lovers_exist", "text": lovers_text, "expires_after_round": None})

    chosen = rng.choice(pool)
    return {
        "type": "hint_reward",
        "hint_id": secrets.token_urlsafe(12),
        "category": chosen["category"],
        "text": chosen["text"],
        "round": G.round,
        "expires_after_round": chosen["expires_after_round"],
    }
