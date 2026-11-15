"""Pydantic response models (request params are declared directly on the routes)."""
from pydantic import BaseModel


class RecordRow(BaseModel):
    branch: str
    subject: str
    year: int
    session: str
    theme: str
    source_table: int


class RecordPage(BaseModel):
    total: int
    page: int
    pages: int
    page_size: int
    rows: list[RecordRow]


class Prediction(BaseModel):
    rank: int
    theme: str
    probability: float          # approx. chance the theme appears in the next sitting (0-1)
    label: str                  # High Probability | Cyclically Due | Moderate | Low
    appearances: int
    last_seen: str
    gap_slots: int
    mean_interval_slots: float | None
    years: list[int]
    breakdown: dict[str, float]  # recency / due / coverage / markov, each 0-1


class PredictionResponse(BaseModel):
    branch: str
    subject: str
    target_session: str
    target_year: int
    level: str                  # "unit" (parent chapter) or "theme" (detailed)
    history_slots: int
    candidates: int
    expected_themes_per_slot: float
    history_reliability: str
    backtest: dict
    predictions: list[Prediction]
