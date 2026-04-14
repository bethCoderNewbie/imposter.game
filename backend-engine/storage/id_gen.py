"""
Game ID generator: 4-char alphanumeric codes for match join screens.
Omits I, O, 0, 1 to eliminate read-aloud confusion.
"""

import secrets

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_game_id() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(4))
