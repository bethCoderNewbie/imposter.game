"""
Unit tests for api.narrator.scripts.get_preset_script().

The DB session factory is fully mocked — no real Postgres connection needed.
asyncio_mode = "auto" (see pyproject.toml) — no @pytest.mark.asyncio needed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


# ── DB mock helpers ───────────────────────────────────────────────────────────


def _script(trigger_id: str, text: str):
    """Build a minimal NarratorScript ORM instance without a real DB session."""
    from storage.models_db import NarratorScript

    s = NarratorScript()
    s.trigger_id = trigger_id
    s.text = text
    return s


def _patch_db(monkeypatch, scripts: list):
    """
    Patch api.narrator.scripts.get_session_factory so that
    ``async with get_session_factory()() as session`` returns a mock session
    whose execute().scalars().all() yields `scripts`.
    """
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = scripts
    session.execute = AsyncMock(return_value=result)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    session_maker = MagicMock(return_value=ctx)
    monkeypatch.setattr(
        "api.narrator.scripts.get_session_factory", lambda: session_maker
    )


# ── Tests ────────────────────────────────────────────────────────────────────


class TestGetPresetScript:
    async def test_returns_text_for_known_trigger(self, monkeypatch):
        from api.narrator.scripts import get_preset_script

        _patch_db(monkeypatch, [_script("game_start", "The village gathers!")])

        result = await get_preset_script("game_start")

        assert result == "The village gathers!"

    async def test_returns_empty_string_when_no_rows(self, monkeypatch):
        from api.narrator.scripts import get_preset_script

        _patch_db(monkeypatch, [])

        result = await get_preset_script("unknown_trigger")

        assert result == ""

    async def test_formats_eliminated_name_placeholder(self, monkeypatch):
        from api.narrator.scripts import get_preset_script

        _patch_db(
            monkeypatch,
            [_script("vote_elimination", "{eliminated_name} has been cast out!")],
        )

        result = await get_preset_script("vote_elimination", eliminated_name="Alice")

        assert result == "Alice has been cast out!"

    async def test_uses_fallback_name_when_eliminated_name_is_none(self, monkeypatch):
        from api.narrator.scripts import get_preset_script

        _patch_db(
            monkeypatch,
            [_script("player_eliminated", "{eliminated_name} was found at dawn!")],
        )

        result = await get_preset_script("player_eliminated", eliminated_name=None)

        assert result == "a player was found at dawn!"

    async def test_returns_one_of_multiple_scripts(self, monkeypatch):
        from api.narrator.scripts import get_preset_script

        texts = ["Line one.", "Line two.", "Line three."]
        _patch_db(
            monkeypatch,
            [_script("game_start", t) for t in texts],
        )

        result = await get_preset_script("game_start")

        assert result in texts

    async def test_no_placeholder_in_plain_text_is_unchanged(self, monkeypatch):
        from api.narrator.scripts import get_preset_script

        _patch_db(monkeypatch, [_script("night_open", "Darkness descends!")])

        result = await get_preset_script("night_open", eliminated_name="Bob")

        # No placeholder — text is returned verbatim
        assert result == "Darkness descends!"

    async def test_randomness_can_return_different_lines(self, monkeypatch):
        """Over many draws from a 2-item pool, both items should appear."""
        from api.narrator.scripts import get_preset_script

        texts = {"First line.", "Second line."}
        _patch_db(
            monkeypatch,
            [_script("wolves_win", t) for t in texts],
        )

        seen = set()
        for _ in range(50):
            seen.add(await get_preset_script("wolves_win"))
            if seen == texts:
                break

        assert seen == texts, "After 50 draws both lines should have appeared"
