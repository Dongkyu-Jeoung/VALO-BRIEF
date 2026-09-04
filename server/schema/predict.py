from pydantic import BaseModel

class Player(BaseModel):
    name: str
    tag: str


class PredictRequest(BaseModel):
    blue_team: list[Player]
    red_team: list[Player]


class TeamSummary(BaseModel):
    acs: float
    kd: float
    kast: float
    winrate: float


class PredictResponse(BaseModel):
    blue_win_probability: float
    predicted_winner: str

    blue_summary: TeamSummary
    red_summary: TeamSummary