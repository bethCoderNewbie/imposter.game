"""
SQLAlchemy ORM models for the persistent player registry and game history.
These tables live in Postgres and persist beyond the Redis 48 h TTL.
"""

from __future__ import annotations

from sqlalchemy import (
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    TIMESTAMP,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DBPlayer(Base):
    """Permanent cross-game player identity."""
    __tablename__ = "players"

    permanent_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[object] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class DBGame(Base):
    """Summary record for every game, written at create and updated at game_over."""
    __tablename__ = "games"

    game_id: Mapped[str] = mapped_column(String(4), primary_key=True)
    started_at: Mapped[object] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    ended_at: Mapped[object] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    winner_team: Mapped[str | None] = mapped_column(String(16), nullable=True)
    player_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class DBGamePlayer(Base):
    """Per-game player record. Linked to both DBGame and DBPlayer."""
    __tablename__ = "game_players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(
        String(4), ForeignKey("games.game_id"), nullable=False
    )
    permanent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("players.permanent_id"), nullable=False
    )
    per_game_player_id: Mapped[str] = mapped_column(String(36), nullable=False)
    role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)

    __table_args__ = (UniqueConstraint("game_id", "permanent_id"),)
