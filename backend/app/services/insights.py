"""Aggregations for the Insights tab. Counts are *distinct sittings* (year, session) per theme,
so the identical rows replicated across branches are never double counted."""
from __future__ import annotations

import pandas as pd

from .data_store import DataStore


def _atoms_frame(store: DataStore, subject: str, branch: str | None,
                 year_min: int | None, year_max: int | None, session: str | None = None,
                 level: str = "unit") -> pd.DataFrame:
    sub = store.filter(branches=[branch] if branch else None, subjects=[subject],
                       sessions=[session] if session else None, year_min=year_min, year_max=year_max)
    col = "unit_atoms" if level == "unit" else "atoms"
    ex = sub[["branch", "year", "session", col]].explode(col).dropna(subset=[col])
    ex = ex.rename(columns={col: "atom"})
    # one row per (year, session, atom): removes cross-branch duplicates when no branch is chosen
    return ex.drop_duplicates(subset=["year", "session", "atom"])


def top_themes(store: DataStore, subject: str, branch: str | None = None,
               years: int = 15, limit: int = 12, level: str = "unit") -> dict:
    ymax = int(store.df["year"].max())
    ymin = ymax - years + 1
    ex = _atoms_frame(store, subject, branch, ymin, ymax, None, level)
    if ex.empty:
        return {"subject": subject, "branch": branch, "from": ymin, "to": ymax, "total_slots": 0, "themes": []}
    total_slots = ex[["year", "session"]].drop_duplicates().shape[0]
    counts = ex.groupby("atom").size().sort_values(ascending=False).head(limit)
    return {"subject": subject, "branch": branch, "from": ymin, "to": ymax, "total_slots": int(total_slots),
            "themes": [{"theme": t, "count": int(c), "share": round(c / total_slots, 3)}
                       for t, c in counts.items()]}


def evolution(store: DataStore, subject: str, branch: str | None = None,
              session: str | None = None, limit: int = 8, level: str = "unit") -> dict:
    ex = _atoms_frame(store, subject, branch, None, None, session, level)
    if ex.empty:
        return {"subject": subject, "years": [], "series": []}
    years = sorted(ex["year"].unique().tolist())
    top = ex.groupby("atom").size().sort_values(ascending=False).head(limit).index
    pivot = (ex[ex.atom.isin(top)].groupby(["year", "atom"]).size().unstack(fill_value=0)
             .reindex(years, fill_value=0))
    return {"subject": subject, "branch": branch, "session": session, "years": [int(y) for y in years],
            "series": [{"theme": t, "data": [int(v) for v in pivot[t].tolist()]} for t in top]}
