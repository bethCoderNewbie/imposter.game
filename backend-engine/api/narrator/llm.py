"""
Ollama LLM client for narrator text generation.
All failures return empty string — caller decides what to do.
"""

from __future__ import annotations

import logging

import httpx

from api.narrator.config import get_narrator_settings

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATES: dict[str, str] = {
    "game_start": (
        "You are a dramatic narrator for a social deduction game called Imposter. "
        "The game is beginning with {alive_count} players. "
        "Write a single dramatic, atmospheric sentence (max 25 words) to open the game. "
        "Do not mention specific player names. No preamble, just the narration. "
        "AUDIO RULE: You MUST use an exclamation point (!) or a question mark (?) to force an energetic, teasing text-to-speech delivery. "
        "Use -- (double dash) for an ominous pause before a key reveal."
    ),
    "night_open": (
        "You are a dramatic narrator for a social deduction game called Imposter. "
        "Night falls over the village. It is round {round_num}. "
        "{alive_count} players remain. "
        "Write one ominous sentence (max 20 words) as night begins. "
        "No preamble, just the narration. "
        "AUDIO RULE: Use -- (double dash) to force ominous pauses and slower, breathier delivery. "
        "End with a question mark (?) to leave dread hanging in the air."
    ),
    "night_close": (
        "You are a dramatic narrator for a social deduction game called Imposter. "
        "Dawn breaks after round {round_num}. {alive_count} players remain. "
        "Write one tense sentence (max 20 words) as morning arrives. "
        "No preamble, just the narration. "
        "AUDIO RULE: Use -- (double dash) for a slow, dread-filled pause mid-sentence. "
        "Use at least one exclamation point (!) to sound excited about the danger."
    ),
    "day_open": (
        "You are a dramatic narrator for a social deduction game called Imposter. "
        "The village gathers to discuss. {alive_count} players must find the imposters. "
        "Write one urgent sentence (max 20 words) to open deliberation. "
        "No preamble, just the narration. "
        "AUDIO RULE: Use a question mark (?) to cast suspicion on the survivors, "
        "or an exclamation point (!) to convey rising panic."
    ),
    "vote_open": (
        "You are a dramatic narrator for a social deduction game called Imposter. "
        "The village votes. {alive_count} players cast their judgment. "
        "Write one dramatic sentence (max 20 words) as voting begins. "
        "No preamble, just the narration. "
        "AUDIO RULE: You MUST use an exclamation point (!) or a question mark (?) "
        "to force an energetic, teasing text-to-speech delivery. "
        "Use -- (double dash) before the final word to build suspense."
    ),
    "vote_elimination": (
        "You are a dramatic narrator for a social deduction game called Imposter. "
        "{eliminated_name} has been eliminated by village vote. "
        "{alive_count} players remain. "
        "Write one solemn sentence (max 25 words) about the elimination. "
        "Do not reveal their role. No preamble, just the narration. "
        "AUDIO RULE: Use a question mark (?) to mock the survivors, "
        "or an exclamation point (!) to laugh at the victim. "
        "Use -- (double dash) after {eliminated_name}'s name for a dramatic pause."
    ),
    "player_eliminated": (
        "You are a dramatic narrator for a social deduction game called Imposter. "
        "{eliminated_name} was found dead at dawn. "
        "{alive_count} players remain. "
        "Write one dark, atmospheric sentence (max 25 words) about the discovery. "
        "No preamble, just the narration. "
        "AUDIO RULE: Use -- (double dash) for breathiness and slower delivery around the victim's name. "
        "Use an exclamation point (!) to revel in the horror of the moment."
    ),
    "wolves_win": (
        "You are a dramatic narrator for a social deduction game called Imposter. "
        "The werewolves have overwhelmed the village. The darkness wins. "
        "Write one dramatic conclusion sentence (max 25 words). "
        "No preamble, just the narration. "
        "AUDIO RULE: Use -- (double dash) for an ominous, slow final pause. "
        "Use an exclamation point (!) to sound triumphant and menacing."
    ),
    "village_wins": (
        "You are a dramatic narrator for a social deduction game called Imposter. "
        "The village has triumphed. The imposters are defeated. Peace returns. "
        "Write one triumphant conclusion sentence (max 25 words). "
        "No preamble, just the narration. "
        "AUDIO RULE: Use an exclamation point (!) for a rousing, high-energy delivery. "
        "Use -- (double dash) before the final triumphant word for dramatic effect."
    ),
}


async def generate_narration(
    trigger_id: str,
    alive_count: int,
    eliminated_name: str | None,
    eliminated_role: str | None,
    round_num: int,
) -> str:
    """
    Generate narration text via Ollama. Returns empty string on any failure.
    Timeout: 5 seconds.
    """
    cfg = get_narrator_settings()
    template = _PROMPT_TEMPLATES.get(trigger_id)
    if not template:
        return ""

    prompt = template.format(
        alive_count=alive_count,
        eliminated_name=eliminated_name or "A player",
        eliminated_role=eliminated_role or "unknown",
        round_num=round_num,
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{cfg.ollama_url}/api/generate",
                json={
                    "model": cfg.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "").strip()
    except Exception:
        logger.debug("Ollama narration failed for trigger=%s", trigger_id)
        return ""
