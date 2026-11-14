"""Theme-recurrence scoring engine (pure Python, no web dependencies).

For one (branch, subject) timeline of slots s_0..s_{n-1} we score every theme for
the *next* slot s_n using four interpretable signals, each scaled to [0, 1]:

  recency   exponentially decayed appearance count (half-life = HALF_LIFE slots)
  due       gap analysis: slots since last appearance vs. the theme's own mean
            recurrence interval (a theme "cyclically due" has gap >= interval)
  coverage  share of all slots in which the theme appeared (core vs marginal);
            blended with the share inside the target session type (Principale vs Contrôle)
  markov    first-order Markov transition: P(theme in next slot | themes in last slot)

Scores are combined linearly, converted to a share, then scaled by k (the typical
number of themes per slot) so that probabilities approximate "chance this theme
appears in the next sitting". This is a transparent heuristic, NOT a trained model:
use `backtest()` to see how it compares with naive baselines on this dataset.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean

HALF_LIFE = 8          # slots (~4 years when Principale+Contrôle both exist)
ACTIVE_WINDOW = 24     # ignore themes not seen in the last N slots (retired)
RETIRED_RATIO = 4      # silent for > 4x its usual interval ...
RETIRED_MIN_GAP = 8    # ... and for at least 8 sittings => treated as retired
WEIGHTS = {"recency": 0.30, "due": 0.25, "coverage": 0.30, "markov": 0.15}


def _expected_k(slots: list[dict], window: int = 10) -> float:
    sizes = [len(s["themes"]) for s in slots[-window:] if s["themes"]]
    return mean(sizes) if sizes else 1.0


def _markov(slots: list[dict]) -> dict[str, float]:
    """P(theme | last slot) averaged over the themes of the last slot."""
    trans: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for prev, nxt in zip(slots, slots[1:]):
        for a in prev["themes"]:
            for b in nxt["themes"]:
                trans[a][b] += 1
    out: dict[str, float] = defaultdict(float)
    rows = [trans[a] for a in slots[-1]["themes"] if a in trans]
    for row in rows:
        tot = sum(row.values())
        for b, c in row.items():
            out[b] += c / tot / len(rows)
    return out


def score_themes(slots: list[dict], target_session: str | None = None,
                 weights: dict | None = None) -> list[dict]:
    """Rank candidate themes for the slot following `slots`. Returns [] if no history."""
    w = weights or WEIGHTS
    n = len(slots)
    if n == 0:
        return []
    appear: dict[str, list[int]] = defaultdict(list)
    for i, s in enumerate(slots):
        for t in s["themes"]:
            appear[t].append(i)
    appear = {t: idx for t, idx in appear.items() if n - idx[-1] <= ACTIVE_WINDOW}
    if not appear:
        return []

    same = [i for i, s in enumerate(slots) if target_session and s["session"] == target_session]
    markov = _markov(slots)
    raw: dict[str, dict] = {}
    for t, idx in appear.items():
        gap = n - idx[-1]                                   # slots until target since last seen
        intervals = [b - a for a, b in zip(idx, idx[1:])]
        mean_int = mean(intervals) if intervals else None
        if (mean_int and gap / mean_int > RETIRED_RATIO and gap >= RETIRED_MIN_GAP) or (not mean_int and gap > 12):
            continue                                        # chapter has left the exams: do not forecast it
        decay = sum(0.5 ** ((n - 1 - i) / HALF_LIFE) for i in idx)
        if mean_int:
            ratio = gap / mean_int
            due = min(ratio, 1.5) / 1.5
            if ratio > 2.5:                                 # probably retired from the programme
                due *= 0.5
        else:
            ratio, due = None, 0.2                          # seen once: weak prior
        cov = len(idx) / n
        if same:
            sess_cov = sum(1 for i in idx if i in set(same)) / len(same)
            cov = 0.5 * cov + 0.5 * sess_cov
        raw[t] = {"recency": decay, "due": due, "coverage": cov, "markov": markov.get(t, 0.0),
                  "gap": gap, "mean_int": mean_int, "ratio": ratio, "idx": idx}

    if not raw:
        return []
    maxes = {f: (max(r[f] for r in raw.values()) or 1.0) for f in w}
    scored = []
    for t, r in raw.items():
        comps = {f: r[f] / maxes[f] for f in w}
        scored.append({"theme": t, "score": sum(w[f] * comps[f] for f in w), "components": comps, **r})
    total = sum(s["score"] for s in scored) or 1.0
    k, n_cand = _expected_k(slots), len(scored)
    for s in scored:
        share = s["score"] / total
        s["probability"] = min(0.95, k * share)
        s["lift"] = share * n_cand                           # vs. uniform guess among candidates
        s["label"] = _label(s)
    scored.sort(key=lambda s: s["score"], reverse=True)
    return scored


def _label(s: dict) -> str:
    appearances = len(s["idx"])
    if s["ratio"] is not None and s["ratio"] >= 0.9 and appearances >= 3 and s["lift"] >= 1.0:
        return "Cyclically Due"
    if s["lift"] >= 2.5 and s["probability"] >= 0.15:
        return "High Probability"
    if s["lift"] >= 1.5:
        return "Moderate"
    return "Low"


def predict(slots: list[dict], target_session: str | None, top_n: int = 10) -> dict:
    ranked = score_themes(slots, target_session)
    n = len(slots)
    last_year = slots[-1]["year"] if slots else None
    out = []
    for rank, s in enumerate(ranked[:top_n], 1):
        years = [slots[i]["year"] for i in s["idx"]]
        out.append({
            "rank": rank, "theme": s["theme"], "probability": round(s["probability"], 4),
            "label": s["label"], "appearances": len(s["idx"]),
            "last_seen": f'{slots[s["idx"][-1]]["year"]} {slots[s["idx"][-1]]["session"]}',
            "gap_slots": s["gap"],
            "mean_interval_slots": round(s["mean_int"], 2) if s["mean_int"] else None,
            "years": years,
            "breakdown": {k: round(v, 3) for k, v in s["components"].items()},
        })
    reliability = "low" if n < 8 else "medium" if n < 14 else "good"
    return {"history_slots": n, "last_year": last_year, "candidates": len(ranked),
            "expected_themes_per_slot": round(_expected_k(slots), 2),
            "history_reliability": reliability, "predictions": out}


def _auc(scores: dict[str, float], actual: set[str]) -> float | None:
    """P(a chapter that really appeared is ranked above one that did not). 0.5 = random guessing.
    Real chapters the model never saw (new in the programme) count as ranked last."""
    neg = [v for t, v in scores.items() if t not in actual]
    if not neg or not actual:
        return None
    wins = 0.0
    for t in actual:
        p = scores.get(t)
        if p is None:
            continue
        wins += sum(1.0 if p > q else 0.5 if p == q else 0.0 for q in neg)
    return wins / (len(actual) * len(neg))


def backtest(slots: list[dict], folds: int = 12) -> dict:
    """Walk-forward evaluation: for each of the last `folds` sittings, fit on the past only and measure
    AUC against (a) a frequency-only baseline and (b) random guessing (0.5)."""
    n = len(slots)
    folds = min(folds, n - 4)
    if folds < 1:
        return {"folds": 0, "note": "Not enough history for backtesting."}
    res: dict[str, list[float]] = {"model": [], "frequency_baseline": []}
    for j in range(n - folds, n):
        actual, hist = slots[j]["themes"], slots[:j]
        if not actual or not hist:
            continue
        a = [_auc({r["theme"]: r["score"] for r in score_themes(hist, slots[j]["session"], w)}, actual)
             for w in (None, {"coverage": 1.0})]
        if None in a:
            continue
        res["model"].append(a[0])
        res["frequency_baseline"].append(a[1])
    if not res["model"]:
        return {"folds": 0, "note": "No evaluable folds."}
    return {"folds": len(res["model"]), "metric": "AUC", "random": 0.5,
            **{k: round(mean(v), 3) for k, v in res.items()}}
