from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_store
from ..models import PredictionResponse
from ..services import insights, predictor
from ..services.data_store import DataStore, SESSION_ORDER, track_of

router = APIRouter(prefix="/api", tags=["analytics"])


def _resolve(store: DataStore, branch: str, subject: str, session: str | None, level: str):
    """Validate the triple and return (target_session, slots-of-its-track)."""
    d = store.df
    sub = d[(d.branch == branch) & (d.subject == subject)]
    if sub.empty:
        raise HTTPException(404, f"No data for branch '{branch}' and subject '{subject}'.")
    available = sorted(sub.session.unique(), key=lambda s: SESSION_ORDER.get(s, 9))
    session = session or available[0]
    if session not in available:
        raise HTTPException(400, f"Session '{session}' not available; choose one of {available}.")
    return session, store.slots(branch, subject, track_of(session), level)


@lru_cache(maxsize=512)
def _cached_predict(branch: str, subject: str, session: str | None, top_n: int, level: str):
    store = get_store()
    session, slots = _resolve(store, branch, subject, session, level)
    out = predictor.predict(slots, session, top_n)
    out["backtest"] = predictor.backtest(slots)
    out["target_session"] = session
    return out


@router.get("/predict", response_model=PredictionResponse)
def predict(branch: str, subject: str, session: str | None = None, top_n: int = Query(10, ge=1, le=50),
            level: str = Query("unit", pattern="^(unit|theme)$")):
    out = _cached_predict(branch, subject, session, top_n, level)
    return {"branch": branch, "subject": subject, "target_year": (out["last_year"] or 0) + 1, "level": level, **out}


@router.get("/insights/top-themes")
def top_themes(subject: str, branch: str | None = None, years: int = Query(15, ge=3, le=40),
               limit: int = Query(12, ge=1, le=30), level: str = Query("unit", pattern="^(unit|theme)$"),
               store: DataStore = Depends(get_store)):
    if subject not in store.df.subject.values:
        raise HTTPException(404, f"Unknown subject '{subject}'.")
    return insights.top_themes(store, subject, branch, years, limit, level)


@router.get("/insights/evolution")
def evolution(subject: str, branch: str | None = None, session: str | None = None,
              limit: int = Query(8, ge=1, le=15), level: str = Query("unit", pattern="^(unit|theme)$"),
              store: DataStore = Depends(get_store)):
    if subject not in store.df.subject.values:
        raise HTTPException(404, f"Unknown subject '{subject}'.")
    return insights.evolution(store, subject, branch, session, limit, level)
