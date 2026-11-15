"""Data-quality audit.  Run after every edit of aliases.csv / hierarchy.csv / the raw file:

    python scripts/clean_csv.py && python scripts/audit_data.py

Exit code 1 if any hard check FAILS. Writes data/audit_report.txt.
Hard checks = logical invariants that must always hold.
Warnings   = things the data itself cannot settle (see review_issues.csv / review_*.csv).
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data"
K4 = ["Branche", "Matière", "Année", "Session"]


def _key(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return re.sub(r"[^\w]+", "", "".join(c for c in s if not unicodedata.combining(c)))


def run() -> tuple[list[tuple[str, bool, str]], list[str]]:
    raw = pd.read_csv(DATA / "bac_repartition_chapitres_clean.csv", encoding="utf-8-sig")
    raw.columns = ["Branche", "Matière", "Année", "Session", "cell", "tab"]
    tidy = pd.read_csv(DATA / "bac_themes_tidy.csv", encoding="utf-8-sig").fillna("")
    wide = pd.read_csv(DATA / "bac_repartition_v2.csv", encoding="utf-8-sig").fillna("")
    aliases = pd.read_csv(DATA / "aliases.csv", encoding="utf-8-sig")
    hier = pd.read_csv(DATA / "hierarchy.csv", encoding="utf-8-sig")
    issues = pd.read_csv(DATA / "review_issues.csv", encoding="utf-8-sig")
    th = tidy[tidy["Type"] == "theme"]
    checks: list[tuple[str, bool, str]] = []
    warns: list[str] = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), "" if ok else str(detail)[:300]))

    # --- structure & reconciliation
    check("raw file: 6 columns, no empty cells", raw.shape[1] == 6 and not raw.isna().any().any())
    rk = set(zip(raw.Branche, raw["Matière"], raw["Année"], raw.Session))
    wk = list(zip(wide.Branche, wide["Matière"], wide["Année"], wide.Session))
    check("app file keeps every raw sitting exactly once", set(wk) == rk and len(wk) == len(set(wk)))
    tt = th.groupby(K4)["Thème"].apply(lambda x: "; ".join(dict.fromkeys(x))).to_dict()
    bad = [k for k, c in zip(wk, wide["Chapitres / Thèmes"]) if c != tt.get(k, "")]
    check("app file themes == tidy file themes", not bad, bad[:3])
    unit_map = th[th["Unité"] != ""].groupby(K4)["Unité"].apply(lambda x: "; ".join(dict.fromkeys(x))).to_dict()
    bad = [k for k, c in zip(wk, wide["Unités"]) if c != unit_map.get(k, "")]
    check("app file units == tidy file units", not bad, bad[:3])
    missing = rk - set(zip(tidy.Branche, tidy["Matière"], tidy["Année"], tidy.Session))
    listed = set(zip(issues[issues.problem == "empty / placeholder"].branch, issues[issues.problem == "empty / placeholder"].subject,
                     issues[issues.problem == "empty / placeholder"].year, issues[issues.problem == "empty / placeholder"].session))
    check("every sitting with no themes is listed in review_issues.csv", missing <= listed, sorted(missing - listed)[:3])
    check("no duplicate tidy rows", not tidy.duplicated().any())

    # --- theme hygiene
    t = th["Thème"]
    check("no empty theme", (t.str.len() > 0).all())
    check("no leftover separators (; | ' / ' ' + ') inside a theme", not t.str.contains(r";|\||\s/\s|\s\+\s").any(),
          t[t.str.contains(r";|\||\s/\s|\s\+\s")].unique()[:5])
    check("no leading/trailing/double spaces", not t.str.contains(r"^\s|\s$|\s\s").any())
    check("no theme that is a single character or only digits", not th[(t.str.len() <= 1) | t.str.fullmatch(r"\d+")].shape[0],
          th[(t.str.len() <= 1) | t.str.fullmatch(r"\d+")]["Thème"].unique())
    check("no digit-prefixed or 'Ex..' leftovers", not t.str.match(r"^(\d|Ex\s?\d)").any(), t[t.str.match(r"^(\d|Ex\s?\d)")].unique()[:5])
    dup = th.assign(k=th["Matière"] + "|" + t.map(_key)).groupby("k")["Thème"].nunique()
    check("one spelling per theme (case/accent/punctuation variants merged)", (dup == 1).all(), dup[dup > 1].index.tolist()[:5])
    check("Type is theme|format only", set(tidy["Type"]) <= {"theme", "format"})

    # --- units
    per = th.groupby(["Matière", "Thème"])["Unité"].nunique()
    check("each theme belongs to exactly one unit", (per == 1).all(), per[per > 1].index.tolist()[:5])
    noun = th[th["Unité"] == ""]
    check("empty unit only for English essay topics", set(noun["Matière"]) <= {"Anglais"} and noun["Format"].str.startswith("Essay").all())
    check("a unit never contains ' : ' (English sub-theme leaked)", not th["Unité"].str.contains(" : ").any())

    # --- combinations (Groupe) and exercises
    g = tidy[tidy["Groupe"] != ""].groupby("Groupe")
    check("every Groupe has >= 2 themes", (g.size() >= 2).all())
    check("a Groupe never spans two sittings", (g.apply(lambda x: len(x[K4].drop_duplicates()), include_groups=False) == 1).all())
    check("no theme twice inside one Groupe", not g.apply(lambda x: x["Thème"].duplicated().any(), include_groups=False).any())
    ex = th[th["Exercice"] != ""]
    bad = [k for k, x in ex.groupby(K4 + ["Discipline", "Exercice"]) if len(x) > 1 and (x["Groupe"].nunique() != 1 or (x["Groupe"] == "").any())]
    check("themes of one exercise (same discipline) share a Groupe", not bad, bad[:3])

    # --- helper files
    check("aliases.csv: no duplicate variants", not aliases.duplicated(["Matière", "Variante"]).any())
    check("aliases.csv: no no-op alias", not (aliases["Variante"].map(_key) == aliases["Canonique"].map(_key)).any())
    known = set(zip(tidy["Matière"], tidy["Thème"].map(_key)))
    dead = [(r.Matière, r.Canonique) for r in aliases.itertuples() if (r.Matière, _key(r.Canonique)) not in known]
    check("aliases.csv: every canonical name exists in the data", not dead, dead)
    bad = [(r.Matière, r.Thème) for r in hier.itertuples() if (r.Matière, _key(r.Thème)) not in known]
    check("hierarchy.csv: every child exists in the data", not bad, bad)
    check("domains: years 2008-2026, 6 branches", tidy["Année"].between(2008, 2026).all() and tidy["Branche"].nunique() == 6)

    # --- warnings (need the real papers / your judgment)
    for p, n in issues.groupby("problem").size().items():
        warns.append(f"{n:>3} x {p}   (see review_issues.csv)")
    ok_short = {"pH", "RC", "RL", "MV", "LC", "Ln", "G", "Int", "Esp"}
    short = sorted(set(t[(t.str.len() <= 3)]) - ok_short)
    warns.append("short/ambiguous fragments to confirm or alias: " + ", ".join(short))
    singles = th.groupby(["Matière", "Thème"]).size()
    warns.append("themes seen only once: " + ", ".join(f"{s}={int((singles[s] == 1).sum())}" for s in singles.index.levels[0]))
    return checks, warns


def main() -> int:
    checks, warns = run()
    lines = [f"{'PASS' if ok else 'FAIL'}  {n}" + (f"\n        -> {d}" if d else "") for n, ok, d in checks]
    lines += ["", "WARNINGS (data limits, not code errors):"] + [f"  - {w}" for w in warns]
    text = "\n".join(lines)
    (DATA / "audit_report.txt").write_text(text, encoding="utf-8")
    print(text)
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
