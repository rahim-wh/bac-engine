"""In-memory dataset: loaded once at startup, queried with vectorised pandas/numpy.

Terminology
-----------
* record : one CSV row (branch x subject x year x session -> raw theme cell)
* atom   : one atomic theme extracted from a raw cell (see themes.py)
* slot   : one exam sitting for a (branch, subject), i.e. a (year, session) pair
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

from .themes import atomize, norm

CSV_PATH = Path(__file__).resolve().parents[2] / "data" / "bac_repartition_v2.csv"

# Chronological order of sessions inside one year.
SESSION_ORDER = {"Principale": 0, "Contrôle": 1, "Toutes": 0,
                 "Partie 1 (تمارين)": 0, "Partie 2 (مواضيع)": 1}
# Only these two sessions form one chronological timeline ("exam" track).
# Other labels (Toutes, Philosophie's Partie 1/2) are independent timelines.
EXAM_SESSIONS = ("Principale", "Contrôle")

SORTABLE = {"branch", "subject", "year", "session", "theme"}


def _fold(s: str) -> str:
    """Lower-case + strip accents/diacritics (Latin & Arabic tashkeel) for search."""
    s = unicodedata.normalize("NFKD", str(s).lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def track_of(session: str) -> str:
    return "exam" if session in EXAM_SESSIONS else session


class DatasetError(RuntimeError):
    pass


class DataStore:
    def __init__(self, path: Path = CSV_PATH):
        if not path.exists():
            raise DatasetError(f"Dataset not found: {path}")
        df = pd.read_csv(path, encoding="utf-8-sig")
        expected = {"Branche", "Matière", "Année", "Session", "Chapitres / Thèmes", "Tableau_source"}
        df.columns = [c.strip().lstrip("\ufeff") for c in df.columns]
        if not expected.issubset(df.columns):
            raise DatasetError(f"Unexpected columns: {list(df.columns)}")
        df = df.rename(columns={"Branche": "branch", "Matière": "subject", "Année": "year",
                                "Session": "session", "Chapitres / Thèmes": "theme",
                                "Tableau_source": "source_table"})
        df["theme"] = df["theme"].fillna("")          # cleaned file leaves unknown cells empty
        for c in ("branch", "subject", "session", "theme"):
            df[c] = df[c].map(norm)
        df["year"] = df["year"].astype(int)
        df["atoms"] = df["theme"].map(atomize)
        # `Unités` = parent chapter of each theme (see scripts/clean_csv.py); fall back to the themes themselves
        units_raw = df["Unités"].fillna("") if "Unités" in df.columns else df["theme"]
        df["unit_atoms"] = [[norm(x) for x in str(u).split(";") if norm(x)] for u in units_raw]
        df["_search"] = (df["branch"] + " " + df["subject"] + " " + df["theme"]).map(_fold)
        df["session_order"] = df["session"].map(SESSION_ORDER).fillna(9).astype(int)
        self.df = df.reset_index(drop=True)
        self._slot_cache: dict[tuple, list[dict]] = {}

    # ------------------------------------------------------------------ meta
    def meta(self) -> dict:
        d = self.df
        subj_by_branch = {b: sorted(g["subject"].unique()) for b, g in d.groupby("branch")}
        sess_by_subject = {s: sorted(g["session"].unique(), key=lambda x: SESSION_ORDER.get(x, 9))
                           for s, g in d.groupby("subject")}
        return {
            "branches": sorted(d["branch"].unique()),
            "subjects": sorted(d["subject"].unique()),
            "sessions": sorted(d["session"].unique(), key=lambda x: SESSION_ORDER.get(x, 9)),
            "year_min": int(d["year"].min()), "year_max": int(d["year"].max()),
            "total_records": int(len(d)),
            "subjects_by_branch": subj_by_branch,
            "sessions_by_subject": sess_by_subject,
        }

    # ------------------------------------------------------------- filtering
    def filter(self, branches=None, subjects=None, sessions=None,
               year_min=None, year_max=None, q: str | None = None) -> pd.DataFrame:
        d = self.df
        mask = np.ones(len(d), dtype=bool)
        if branches:
            mask &= d["branch"].isin(branches).to_numpy()
        if subjects:
            mask &= d["subject"].isin(subjects).to_numpy()
        if sessions:
            mask &= d["session"].isin(sessions).to_numpy()
        if year_min is not None:
            mask &= (d["year"] >= year_min).to_numpy()
        if year_max is not None:
            mask &= (d["year"] <= year_max).to_numpy()
        if q and q.strip():
            # every whitespace-separated term must match (AND semantics)
            for term in _fold(q).split():
                mask &= d["_search"].str.contains(re.escape(term), regex=True).to_numpy()
        return d[mask]

    def query(self, *, sort_by="year", order="desc", page=1, page_size=25, **filters) -> dict:
        sub = self.filter(**filters)
        if sort_by not in SORTABLE:
            sort_by = "year"
        keys = [sort_by] + (["session_order"] if sort_by == "year" else [])
        sub = sub.sort_values(keys, ascending=(order == "asc"), kind="stable")
        total = len(sub)
        page_size = max(1, min(page_size, 500))
        pages = max(1, -(-total // page_size))
        page = max(1, min(page, pages))
        chunk = sub.iloc[(page - 1) * page_size: page * page_size]
        rows = chunk[["branch", "subject", "year", "session", "theme", "source_table"]].to_dict("records")
        return {"total": total, "page": page, "pages": pages, "page_size": page_size, "rows": rows}

    # ---------------------------------------------------------------- slots
    def slots(self, branch: str, subject: str, track: str, level: str = "unit") -> list[dict]:
        """Chronological sittings for one (branch, subject, track); each holds its set of themes
        (level="theme") or of parent chapters (level="unit")."""
        col = "unit_atoms" if level == "unit" else "atoms"
        key = (branch, subject, track, col)
        if key in self._slot_cache:
            return self._slot_cache[key]
        d = self.df[(self.df.branch == branch) & (self.df.subject == subject)]
        d = d[d.session.map(track_of) == track]
        out = []
        for (year, so, session), g in d.groupby(["year", "session_order", "session"], sort=True):
            themes = {a for atoms in g[col] for a in atoms}
            if not themes:      # content unknown (placeholder / essays only): not evidence of absence, skip it
                continue
            out.append({"year": int(year), "session": session, "themes": themes})
        self._slot_cache[key] = out
        return out
