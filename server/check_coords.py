import requests
import json
from database.connection import SessionLocal
from sqlalchemy import text

maps = requests.get("https://valorant-api.com/v1/maps").json()["data"]
target = next(m for m in maps if m["displayName"] == "Split")
print("SPLIT COEFFS:", {
    "xMultiplier": target["xMultiplier"],
    "yMultiplier": target["yMultiplier"],
    "xScalarToAdd": target["xScalarToAdd"],
    "yScalarToAdd": target["yScalarToAdd"],
})

db = SessionLocal()
row = db.execute(
    text("SELECT round_detail_json FROM matches WHERE map_uuid = :uuid LIMIT 1"),
    {"uuid": target["uuid"]},
).fetchone()

if not row:
    print("스플릿 매치를 DB에서 못 찾음")
else:
    rounds = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    found = None
    for rnd in rounds:
        for ps in (rnd.get("player_stats") or []):
            for k in (ps.get("kill_events") or []):
                loc = k.get("victim_death_location")
                if loc:
                    found = loc
                    break
            if found:
                break
        if found:
            break
    print("RAW WORLD COORD:", found)

    print("UUID:", target["uuid"])
    print("DISPLAY ICON URL:", target["displayIcon"])

db.close()