"""
Postgres write helpers for game history.
Called from game_queue on GAME_OVER; never blocks the Redis-backed intent loop.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from engine.state.models import MasterGameState
from storage.db import get_session_factory
from storage.models_db import DBGame, DBGamePlayer


def _outcome(team: str | None, winner: str | None) -> str | None:
    if team is None or winner is None:
        return None
    return "won" if team == winner else "lost"


async def record_game_over(G: MasterGameState) -> None:
    """
    Update the DBGame row with ended_at + winner_team, and set role/outcome
    on each DBGamePlayer. Called as a fire-and-forget background task.
    """
    async with get_session_factory()() as db:
        game_rec = await db.get(DBGame, G.game_id)
        if game_rec:
            game_rec.ended_at = datetime.now(UTC)
            game_rec.winner_team = G.winner

        for pid, ps in G.players.items():
            result = await db.execute(
                select(DBGamePlayer).where(
                    DBGamePlayer.game_id == G.game_id,
                    DBGamePlayer.per_game_player_id == pid,
                )
            )
            row = result.scalar_one_or_none()
            if row:
                row.role = ps.role
                row.outcome = _outcome(ps.team, G.winner)

        await db.commit()
