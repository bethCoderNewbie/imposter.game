"""
Narrator trigger pipeline: LLM → TTS → unicast to display client.
Fire-and-forget: all exceptions caught internally, game continues silently.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from api.narrator.llm import generate_narration
from api.narrator.tts import synthesize

if TYPE_CHECKING:
    from api.connection_manager import ConnectionManager
    from engine.state.models import MasterGameState

logger = logging.getLogger(__name__)


async def narrate(
    trigger_id: str,
    G: "MasterGameState",
    connection_manager: "ConnectionManager",
    game_id: str,
    eliminated_name: str | None = None,
    eliminated_role: str | None = None,
) -> None:
    """
    Fire-and-forget narrator pipeline.
    Generates narration text via Ollama, synthesizes via Kokoro TTS,
    then unicasts the result to the display client (player_id=None).
    All exceptions caught — game continues silently on any failure.
    """
    try:
        alive_count = sum(1 for p in G.players.values() if p.is_alive)
        text = await generate_narration(
            trigger_id,
            alive_count=alive_count,
            eliminated_name=eliminated_name,
            eliminated_role=eliminated_role,
            round_num=G.round,
        )
        if not text:
            return

        audio_url, duration_ms = await synthesize(text)

        phase_str = G.phase.value if hasattr(G.phase, "value") else str(G.phase)
        msg = {
            "type": "narrate",
            "trigger": trigger_id,
            "text": text,
            "audio_url": audio_url,
            "duration_ms": duration_ms,
            "phase": phase_str,
            "round": G.round,
        }
        # Display client is registered with player_id=None in ConnectionManager
        await connection_manager.unicast(game_id, None, msg)
    except Exception:
        logger.debug("Narrator pipeline failed for trigger=%s game=%s", trigger_id, game_id)
