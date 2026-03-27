"""
Loads docs/architecture/roles.json at module import time.
Fails fast at startup if the file is missing or malformed — never at request time.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Resolve path relative to this file: backend-engine/engine/ -> project root -> docs/
_ROLES_PATH = Path(__file__).parent.parent.parent / "docs" / "architecture" / "roles.json"


def _load() -> dict[str, Any]:
    if not _ROLES_PATH.exists():
        raise ValueError(f"roles.json not found at {_ROLES_PATH}")
    with _ROLES_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    required_keys = {"roles", "nightResolutionOrder", "winConditions", "dynamicTemplates", "balanceWeightSystem"}
    missing = required_keys - data.keys()
    if missing:
        raise ValueError(f"roles.json missing top-level keys: {missing}")
    return data


_data = _load()

# Public constants — imported by engine modules
ROLE_REGISTRY: dict[str, dict[str, Any]] = {r["id"]: r for r in _data["roles"]}
NIGHT_RESOLUTION_ORDER: list[dict[str, Any]] = _data["nightResolutionOrder"]
WIN_CONDITIONS: dict[str, Any] = _data["winConditions"]
DYNAMIC_TEMPLATES: list[dict[str, Any]] = _data["dynamicTemplates"]
BALANCE_WEIGHT_SYSTEM: dict[str, Any] = _data["balanceWeightSystem"]

# Derived lookup: role_id -> wakeOrder
WAKE_ORDER: dict[str, int] = {r["id"]: r["wakeOrder"] for r in _data["roles"]}

# Roles that provide a stripped, client-safe view (strip sensitive nightAction details)
CLIENT_SAFE_ROLE_REGISTRY: dict[str, dict[str, Any]] = {
    role_id: {
        "id": r["id"],
        "name": r["name"],
        "team": r["team"],
        "description": r["description"],
        "abilities": r["abilities"],
        "uiPromptNight": r.get("uiPromptNight", ""),
        "ui": r.get("ui", {}),
    }
    for role_id, r in ROLE_REGISTRY.items()
}
