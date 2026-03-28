"""
Archive puzzle resolver: validates player answers against server-side correct_index.
correct_index is NEVER sent to clients — only validated here server-side.
Pure function — no I/O.
"""

from __future__ import annotations

from engine.state.models import MasterGameState


class PuzzleError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def resolve_puzzle_answer(
    G: MasterGameState,
    player_id: str,
    answer_index: int | None = None,
    answer_sequence: list[str] | None = None,
) -> tuple[MasterGameState, bool]:
    """
    Validate a puzzle answer for a wakeOrder==0 player.
    Returns (new_state, is_correct).

    SECURITY: correct_index is read from puzzle_state.puzzle_data which is stored
    server-side only. It is stripped from the puzzle_data before sending to clients.

    Caller is responsible for:
    - Delivering HintPayload to the player if is_correct
    - Checking night_actions.false_hint_queued and broadcasting FalseHintPayload if set
    """
    G = G.model_copy(deep=True)

    player = G.players.get(player_id)
    if not player:
        raise PuzzleError("PLAYER_NOT_FOUND", f"Player {player_id} not found.")

    puzzle = G.players[player_id].puzzle_state
    if not puzzle:
        raise PuzzleError("NO_PUZZLE_ACTIVE", "No puzzle is active for this player.")
    if not puzzle.active:
        raise PuzzleError("PUZZLE_NOT_ACTIVE", "Puzzle is no longer active.")
    if puzzle.solved is not None:
        raise PuzzleError("PUZZLE_ALREADY_SOLVED", "Puzzle has already been answered.")

    is_correct = False

    if puzzle.puzzle_type in ("math", "logic"):
        correct_index = puzzle.puzzle_data.get("correct_index")
        if correct_index is None:
            raise PuzzleError("PUZZLE_DATA_ERROR", "Puzzle data missing correct_index (server error).")
        is_correct = answer_index == correct_index

    elif puzzle.puzzle_type == "sequence":
        correct_sequence = puzzle.puzzle_data.get("sequence", [])
        is_correct = answer_sequence == correct_sequence

    puzzle.active = False
    puzzle.solved = is_correct

    if is_correct:
        player.puzzles_solved_count += 1

    return G, is_correct
