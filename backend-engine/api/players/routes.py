"""
Player registry endpoints: register a permanent player identity, look it up,
and update the display name.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from storage.db import get_db
from storage.models_db import DBPlayer

router = APIRouter(prefix="/api/players", tags=["players"])


class RegisterRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=16)


class UpdateNameRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=16)


@router.post("/register")
async def register_player(
    body: RegisterRequest, db: AsyncSession = Depends(get_db)
):
    """Create a permanent player identity. Returns permanent_id for localStorage."""
    permanent_id = str(uuid.uuid4())
    db.add(DBPlayer(
        permanent_id=permanent_id,
        display_name=body.display_name.strip(),
        created_at=datetime.now(UTC),
    ))
    await db.commit()
    return {"permanent_id": permanent_id, "display_name": body.display_name.strip()}


@router.get("/{permanent_id}")
async def get_player(permanent_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch a player's registered name by their permanent_id."""
    player = await db.get(DBPlayer, permanent_id)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found.")
    return {"permanent_id": player.permanent_id, "display_name": player.display_name}


@router.put("/{permanent_id}")
async def update_player_name(
    permanent_id: str,
    body: UpdateNameRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update a player's display name. Takes effect on future game joins."""
    player = await db.get(DBPlayer, permanent_id)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found.")
    player.display_name = body.display_name.strip()
    await db.commit()
    return {"permanent_id": player.permanent_id, "display_name": player.display_name}
