"""
Narrator trigger pipeline: LLM → TTS → unicast to display client.
Fire-and-forget: all exceptions caught internally, game continues silently.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from api.narrator.config import get_narrator_settings
from api.narrator.llm import generate_narration
from api.narrator.scripts import get_preset_script
from api.narrator.tts import pick_prebaked, synthesize

if TYPE_CHECKING:
    from api.connection_manager import ConnectionManager
    from engine.state.models import MasterGameState

logger = logging.getLogger(__name__)

# (trigger_id, eliminated_name, eliminated_role)
NarrateSpec = tuple[str, str | None, str | None]


async def narrate(
    trigger_id: str,
    G: "MasterGameState",
    connection_manager: "ConnectionManager",
    game_id: str,
    eliminated_name: str | None = None,
    eliminated_role: str | None = None,
) -> int:
    """
    Narrator pipeline with DB fallback.
    Returns duration_ms on success, 0 if skipped.
    Mode controlled by NARRATOR_MODE env var:
      auto   — try Ollama first, fall back to DB preset on failure
      live   — Ollama only, no DB fallback
      static — skip Ollama entirely, always use DB preset
    """
    try:
        cfg = get_narrator_settings()
        alive_count = sum(1 for p in G.players.values() if p.is_alive)
        text = ""

        if cfg.narrator_mode == "prebaked":
            # Text: DB preset with real eliminated_name for subtitle display.
            # Audio: pre-baked WAV uses "a player" (generic — see ADR-021).
            text = await get_preset_script(trigger_id, eliminated_name)
            if not text:
                return 0
            audio_url, duration_ms = await pick_prebaked(trigger_id)

        else:
            if cfg.narrator_mode != "static":
                text = await generate_narration(
                    trigger_id,
                    alive_count=alive_count,
                    eliminated_name=eliminated_name,
                    eliminated_role=eliminated_role,
                    round_num=G.round,
                )

            if not text and cfg.narrator_mode != "live":
                text = await get_preset_script(trigger_id, eliminated_name)

            if not text:
                return 0

            audio_url, duration_ms = await synthesize(text)
        phase_str = G.phase.value if hasattr(G.phase, "value") else str(G.phase)
        await connection_manager.unicast(game_id, None, {
            "type": "narrate",
            "trigger": trigger_id,
            "text": text,
            "audio_url": audio_url,
            "duration_ms": duration_ms,
            "phase": phase_str,
            "round": G.round,
        })
        return duration_ms
    except Exception:
        logger.warning("Narrator pipeline failed for trigger=%s game=%s", trigger_id, game_id, exc_info=True)
        return 0


async def narrate_sequence(
    specs: list[NarrateSpec],
    G: "MasterGameState",
    connection_manager: "ConnectionManager",
    game_id: str,
) -> None:
    """Play narrator triggers in order, waiting for each audio to finish before starting next."""
    for trigger_id, eliminated_name, eliminated_role in specs:
        duration_ms = await narrate(
            trigger_id, G, connection_manager, game_id,
            eliminated_name=eliminated_name,
            eliminated_role=eliminated_role,
        )
        if duration_ms > 0:
            await asyncio.sleep(duration_ms / 1000 + 0.3)  # 300 ms buffer between lines
