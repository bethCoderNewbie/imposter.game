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


def _make_logic_question(rng: random.Random) -> dict:
    """Build one 4-option logic Q&A dict with correct_index. Shared by logic/hard_logic."""
    q_idx = rng.randrange(len(BANK))
    question, correct_answer, category = BANK[q_idx]

    peers = [i for i in BANK_BY_CATEGORY.get(category, []) if i != q_idx]
    distractor_indices = rng.sample(peers, min(3, len(peers)))
    distractors = [BANK[i][1] for i in distractor_indices]

    seen = {correct_answer} | set(distractors)
    while len(distractors) < 3:
        d_idx = rng.randrange(len(BANK))
        candidate = BANK[d_idx][1]
        if candidate not in seen:
            distractors.append(candidate)
            seen.add(candidate)

    options = [correct_answer] + distractors
    rng.shuffle(options)
    return {"question": question, "answer_options": options, "correct_index": options.index(correct_answer)}


def _make_logic_puzzle(rng: random.Random) -> "PuzzleState":
    from engine.state.models import PuzzleState

    return PuzzleState(
        puzzle_type="logic",
        puzzle_data=_make_logic_question(rng),
        time_limit_seconds=20,
    )


def _make_hard_logic_puzzle(rng: random.Random) -> "PuzzleState":
    """Two sequential logic questions — both must be answered correctly. 20s shared."""
    from engine.state.models import PuzzleState

    return PuzzleState(
        puzzle_type="hard_logic",
        puzzle_data={"q1": _make_logic_question(rng), "q2": _make_logic_question(rng)},
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


# Hint generation has moved to engine/hint_bank.py.
# Import from there: from engine.hint_bank import generate_hint, generate_grid_hint


# ── Grid system ───────────────────────────────────────────────────────────────

def generate_grid_layout(seed: str, round_number: int) -> list[list[int]]:
    """
    Generate a 5×5 tier grid for a night round. Deterministic given (seed, round).
    Distribution: exactly 1 red (tier 3), 6 yellow (tier 2), 18 green (tier 1).
    Returns a list of 5 rows, each a list of 5 tier integers.
    """
    rng = random.Random(f"{seed}:{round_number}:grid_layout")
    cells = [1] * 18 + [2] * 6 + [3] * 1  # 25 cells total
    rng.shuffle(cells)
    return [cells[i * 5:(i + 1) * 5] for i in range(5)]


def generate_grid_puzzle(tier: int, rng: random.Random) -> "PuzzleState":
    """
    Generate a PuzzleState appropriate for a node of the given tier.

    Tier 1 (green, 5s):  Simple math puzzle.
    Tier 2 (yellow, 10s): Logic puzzle (multiple choice from BANK).
    Tier 3 (red, 20s):   Logic puzzle with full time window.
    """
    if tier == 1:
        puzzle = _make_math_puzzle(rng, round_number=1)  # round_number=1 → simple operations
        return puzzle.model_copy(update={"time_limit_seconds": 5})
    if tier == 2:
        puzzle = _make_logic_puzzle(rng)
        return puzzle.model_copy(update={"time_limit_seconds": 10})
    # Tier 3
    return _make_hard_logic_puzzle(rng)


def node_to_quadrant(row: int, col: int) -> str:
    """
    Map a (row, col) in the 5×5 grid to one of four quadrant names.
    Rows 0–1 = top; rows 2–4 = bottom.
    Cols 0–1 = left; cols 2–4 = right.
    """
    top = row <= 1
    left = col <= 1
    if top and left:
        return "top_left"
    if top:
        return "top_right"
    if left:
        return "bottom_left"
    return "bottom_right"
