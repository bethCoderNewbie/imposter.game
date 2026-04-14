"""
Pre-seeded narrator script fetcher.
Returns a random preset line for a given trigger_id from the DB,
or empty string if none exist.
"""

from __future__ import annotations

import random

from sqlalchemy import select

from storage.db import get_session_factory
from storage.models_db import NarratorScript


async def get_preset_script(
    trigger_id: str,
    eliminated_name: str | None = None,
    index: int | None = None,
) -> str:
    """Return a preset line for trigger_id, or '' if none exist.

    If index is given (prebaked mode), select the row at that position
    (ORDER BY id) so the subtitle matches the pre-generated WAV file.
    If index is None (auto/static fallback), pick randomly.
    """
    async with get_session_factory()() as session:
        rows = await session.execute(
            select(NarratorScript)
            .where(NarratorScript.trigger_id == trigger_id)
            .order_by(NarratorScript.id)
        )
        scripts = rows.scalars().all()
    if not scripts:
        return ""
    chosen = scripts[index % len(scripts)] if index is not None else random.choice(scripts)
    return chosen.text.format(eliminated_name=eliminated_name or "a player")
