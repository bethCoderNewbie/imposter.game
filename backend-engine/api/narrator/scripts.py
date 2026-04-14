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
) -> str:
    """Return a random preset line for trigger_id, or '' if none exist."""
    async with get_session_factory()() as session:
        rows = await session.execute(
            select(NarratorScript).where(NarratorScript.trigger_id == trigger_id)
        )
        scripts = rows.scalars().all()
    if not scripts:
        return ""
    text = random.choice(scripts).text
    return text.format(eliminated_name=eliminated_name or "a player")
