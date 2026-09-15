"""Container smoke check; no external API calls or DB writes."""
import asyncio
import numpy as np
import pandas as pd
from sqlalchemy import text

from main import app, health
from database.connection import engine
from ml.model_loader import get_model, get_feature_columns
from ml.engagement_predictor import _get_artifact

assert asyncio.run(health()) == {"status": "ok"}
features = get_feature_columns()
result = get_model().predict_proba(pd.DataFrame([[1.0] * len(features)], columns=features))
assert np.isfinite(result).all()
artifact = _get_artifact()
assert artifact is not None, "Engagement model failed to load"
with engine.connect() as connection:
    assert connection.execute(text("SELECT 1")).scalar() == 1
    connection.execute(text("SELECT * FROM insights LIMIT 0"))
print("PASS: app import, health, prediction inference, engagement model, MySQL connection")
