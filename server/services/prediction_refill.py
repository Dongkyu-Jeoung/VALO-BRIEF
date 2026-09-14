"""Compatibility entry points for the retired raw-match DB refill worker.

Premier prediction uses API data. Raw match storage is disabled, so callers of
these legacy entry points must not trigger API requests or background DB writes.
"""

_DISABLED = "[DB REFILL] Disabled: raw match storage is no longer maintained."


async def refill(team_id, team_name, team_tag, puuids, checkpoint):
    checkpoint(_DISABLED)


def schedule_refill(team_id, team_name, team_tag, puuids, checkpoint):
    checkpoint(_DISABLED)
