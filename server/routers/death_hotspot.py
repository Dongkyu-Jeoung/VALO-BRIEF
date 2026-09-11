# server/routers/death_hotspot.py

from fastapi import APIRouter
from schema.death_event import DeathHotspotResponse
from services.death_hotspot_service import get_death_hotspots

router = APIRouter()

@router.get("/teams/{team_id}/maps/{map_id}/death-hotspots", response_model=DeathHotspotResponse)
def death_hotspots(team_id: str, map_id: str):
    hotspots = get_death_hotspots(team_id, map_id)
    return {"mapId": map_id, "hotspots": hotspots}