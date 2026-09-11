# server/schema/death_event.py

from pydantic import BaseModel
from typing import List

class DeathHotspot(BaseModel):
    playerId: str
    playerName: str
    x: float
    y: float
    deathCount: int

class DeathHotspotResponse(BaseModel):
    mapId: str
    hotspots: List[DeathHotspot]