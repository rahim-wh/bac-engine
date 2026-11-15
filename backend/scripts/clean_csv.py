"""Clean the raw Bac CSV. The original file is never modified.

    python scripts/clean_csv.py

Reads  data/bac_repartition_chapitres_clean.csv   (raw, 1 row = 1 exam cell)
       data/aliases.csv                           (YOUR decisions: variant -> canonical theme)
Writes data/bac_themes_tidy.csv        one row per atomic theme (+ exercise / combination info)
       data/bac_repartition_v2.csv     same 6 columns as the raw file, canonical themes joined by '; '
                                       (this is the file the web app loads)
       data/review_aliases.csv         theme names that look like the same thing -> decide, add to aliases.csv
       data/review_issues.csv          rows with missing/placeholder content -> fill from the real papers

Tidy columns
  Type        theme | format   (format = QCM, V/F, Document, paragraph, article... NOT a chapter)
  Groupe      pieces split from ONE written token share a Groupe id (e.g. "Alcool et Dosage",
              "pH/Dosage"): the raw material for combination analysis later.
  Exercice    exercise number when the source gives it (Maths, SVT par exercice)
  Document    1 if the theme appeared as a document-analysis exercise ("(doc)")
  Discipline  Physique | Chimie when the source labels it
  Origine     the exact original token, for traceability
"""
from __future__ import annotations

import collections
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data"
RAW = DATA / "bac_repartition_chapitres_clean.csv"
ALIASES = DATA / "aliases.csv"

SPLIT_SUBJECTS = {"Physique-Chimie", "Physique", "Mathématiques (par exercice)"}  # also split '/' ',' ' et '
PLACEHOLDER = re.compile(r"^\W*$|aucun|non renseign", re.I)
ENGLISH_FORMATS = {"paragraph", "article", "essay", "graph", "facebook post", "e-magazine article"}

LABEL = re.compile(r"(Phy|Physique|Chi|Chimie)\s*:\s*", re.I)
PIECE_SPLIT = re.compile(r"\s*(?:,|/|\+|;|\bet\b)\s*")


# ----------------------------------------------------------------------------- helpers
def norm(s) -> str:
    s = unicodedata.normalize("NFC", "" if pd.isna(s) else str(s))
    return re.sub(r"\s+", " ", s).strip()


def key(s: str) -> str:
    """Matching key: no accents, lower case, only letters/digits (Latin + Arabic)."""
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^\w]+", "", s)


def clean_piece(p: str) -> str:
    return norm(p).strip(" .,:;-")


def split_pieces(token: str, aggressive: bool) -> list[str]:
    parts = PIECE_SPLIT.split(token) if aggressive else [token]
    return [clean_piece(x) for x in parts if clean_piece(x)]


def row(**kw):
    base = dict(theme="", type="theme", format="", discipline="", exercice="", group="", doc=0, note="", origin="")
    base.update(kw)
    return base


# ----------------------------------------------------------------------------- parsers
def parse_cell(subject: str, raw: str, gid) -> list[dict]:
    """Return the atomic rows of one raw cell. `gid` yields fresh Groupe ids."""
    raw = norm(raw)
    if PLACEHOLDER.search(raw) and len(raw) < 30:
        return []
    if subject == "Philosophie (الفلسفة)":
        return [row(theme=clean_piece(p), origin=raw) for p in raw.split(" / ") if clean_piece(p)]
    if subject == "Anglais":
        return parse_english(raw)
    if subject == "Français":                       # one cell can hold two themes: "A / B"
        pieces = [clean_piece(p) for p in re.sub(r"^Thème officiel\s*:\s*", "", raw).split(" / ") if clean_piece(p)]
        g = gid() if len(pieces) > 1 else ""
        return [row(theme=p, group=g, origin=raw) for p in pieces]
    if subject.startswith("Arabe") or subject in ("Allemand", "Espagnol", "Italien"):
        th, note = extract_note(raw)
        return [row(theme=clean_piece(th), note=note, origin=raw)]
    if subject == "SVT (par exercice)":
        return parse_svt_exercise(raw, gid)
    if subject == "Mathématiques (par exercice)":
        return parse_math_exercise(raw, gid)
    if subject == "Mathématiques":
        return parse_math(raw, gid)
    if subject in ("Physique-Chimie", "Physique"):
        return parse_physics(subject, raw, gid)
    # SVT par chapitre, Génie électrique/mécanique: ';' or ' + ' lists (no '/' splitting: it is part of names)
    out = []
    for tok in re.split(r"\s*(?:;|\s\+\s)\s*", raw):
        m = re.match(r"^(Transmission|Transformation)/(transmission|transformation) de mvt$", norm(tok), re.I)
        if m:
            g = gid()
            for w in (m.group(1), m.group(2)):
                out.append(row(theme=f"{w.capitalize()} de mvt", group=g, origin=tok))
            continue
        for th, doc, note in doc_flag(tok):
            out.append(row(theme=th, doc=doc, note=note, origin=tok))
    return out


NOTE = re.compile(r"\s*\((hors programme|partiellement masqué)\)", re.I)


def extract_note(tok: str) -> tuple[str, str]:
    """'Schule und Beruf (hors programme)' -> ('Schule und Beruf', 'hors programme')."""
    notes = [n.lower() for n in NOTE.findall(tok)]
    return NOTE.sub("", tok), "; ".join(notes)


def doc_flag(tok: str):
    """'Nucl.(doc)' -> ('Nucl', 1, ''). 'doc(Cond)' -> ('Cond', 1, ''). Returns [(theme, doc, note)]."""
    tok = norm(tok)
    m = re.match(r"^doc\((.+)\)$", tok, re.I)
    if m:
        return [(clean_piece(m.group(1)), 1, "")]
    tok, note = extract_note(tok)
    doc = 1 if re.search(r"\(doc\)", tok, re.I) else 0
    tok = re.sub(r"\s*\(doc\)", "", tok, flags=re.I)
    tok = re.sub(r"\s*\(\d+\)", "", tok)
    tok = clean_piece(tok)
    return [(tok, doc, note)] if tok else []


PROTECTED = [(re.compile(r"Franck\s*\+\s*Hertz", re.I), "Franck-Hertz"),      # one experiment, not two themes
             (re.compile(r"LC\s*\+\s*entret\.?", re.I), "LC entretenu")]       # LC oscillator, sustained


def parse_physics(subject: str, raw: str, gid) -> list[dict]:
    out = []
    for pat, repl in PROTECTED:
        raw = pat.sub(repl, raw)
    labelled = list(LABEL.finditer(raw))
    if labelled:   # old format: "Phy: RLC/Conv/onde | Chi: Alcool et Dosage"  or  "Chimie: A, B / Physique: C, Document"
        for i, m in enumerate(labelled):
            end = labelled[i + 1].start() if i + 1 < len(labelled) else len(raw)
            body = re.sub(r"\s*(?:\||/)\s*$", "", raw[m.end():end]).strip()
            disc = "Physique" if m.group(1).lower().startswith("phy") else "Chimie"
            out += _physics_body(body, disc, gid)
    else:          # checkbox format: "RC; Ondes; Nucl.(doc); pH/Dosage"
        for tok in raw.split(";"):
            out += _physics_body(tok, "", gid, per_token_group=True)
    return out


def _physics_body(body: str, disc: str, gid, per_token_group=False) -> list[dict]:
    out = []
    if re.match(r"^\s*\d\s*/", body):          # "1/RC+Elec 2/Nucl 3/Onde": leading digit = exercise number
        parts = re.split(r"(?<!\w)(\d)\s*/\s*", body)
        for n, text in zip(parts[1::2], parts[2::2]):
            for r in _physics_body(text.strip(), disc, gid, per_token_group=True):
                r["exercice"] = f"Ex{n}"
                out.append(r)
        return _group_by_exercise_pieces(out)
    # "Alcool et Dosage" / "pH/Dosage" / "RL/MV(AOp)/onde": one token -> several themes
    for tok in (re.split(r"\s*,\s*", body) if not per_token_group else [body]):
        tok = norm(tok)
        if not tok:
            continue
        pieces = [clean_piece(p) for p in re.split(r"\s*(?:/|\+|;|\bet\b)\s*", tok) if clean_piece(p)]
        g = gid() if len(pieces) > 1 else ""
        for p in pieces:
            if re.fullmatch(r"documents?", p, re.I):
                out.append(row(theme="Document", type="format", discipline=disc, origin=tok)); continue
            for th, doc, note in doc_flag(p):
                out.append(row(theme=th, doc=doc, note=note, discipline=disc, group=g, origin=tok))
    return out


def _group_by_exercise_pieces(rows: list[dict]) -> list[dict]:
    return rows


def parse_math(raw: str, gid) -> list[dict]:
    """'Complexes (Ex1:3); Similitudes (Ex1:1)'  |  'Complexe; Arithm.; Matrice'  |  'QCM proba + complexe + exp'."""
    out = []
    for tok in re.split(r"\s*(?:;|\s\+\s)\s*", raw):
        tok = norm(tok)
        m = re.match(r"^(.*?)\s*\(Ex\s*(\d+)\s*:\s*(\d+)\)$", tok)
        if m:
            out.append(row(theme=clean_piece(m.group(1)), exercice=f"Ex{m.group(2)}", origin=tok))
            continue
        q = re.match(r"^QCM\b\s*(.*)$", tok)
        if q:
            out.append(row(theme="QCM", type="format", origin=tok))
            tok = q.group(1)
        if clean_piece(tok):
            out.append(row(theme=clean_piece(tok), origin=tok))
    return _group_by_exercise(out, gid)


def _group_by_exercise(rows: list[dict], gid) -> list[dict]:
    """Themes sharing one exercise are a combination: give them one Groupe id."""
    by_ex = collections.defaultdict(list)
    for r in rows:
        if r["exercice"] and r["type"] == "theme":
            by_ex[r["exercice"]].append(r)
    for rs in by_ex.values():
        if len(rs) > 1:
            g = gid()
            for r in rs:
                r["group"] = g
    return rows


def parse_math_exercise(raw: str, gid) -> list[dict]:
    """'Ex1: QCM (Comp+eq) | Ex2: ln+gr | Ex4-5: Esp (4) Stat (5)'."""
    out = []
    for seg in raw.split("|"):
        m = re.match(r"^\s*Ex\s*([\d\-]+)\s*:\s*(.*)$", seg.strip(), re.I)
        if not m:
            continue
        ex, body = f"Ex{m.group(1)}", norm(m.group(2))
        if clean_piece(body) == "":
            continue
        fm = re.match(r"^(QCM|V/F)\s*(?:\((.*)\))?$", body)
        if fm:
            out.append(row(theme=fm.group(1), type="format", exercice=ex, origin=seg.strip()))
            body = fm.group(2) or ""
        numbered = re.findall(r"([^()]+?)\s*\((\d)\)", body)       # "Esp (4) Stat (5)"
        if numbered:
            for th, n in numbered:
                out.append(row(theme=clean_piece(th), exercice=f"Ex{n}", origin=seg.strip()))
            continue
        pieces = [clean_piece(p) for p in re.split(r"\s*(?:/|\+(?!\s*gr\b))\s*", body) if clean_piece(p)]
        g = gid() if len(pieces) > 1 else ""
        for p in pieces:
            out.append(row(theme=p, exercice=ex, group=g, origin=seg.strip()))
    return out


def parse_svt_exercise(raw: str, gid) -> list[dict]:
    out = []
    if re.match(r"^\s*Ex\s*\d", raw, re.I):       # 2026 format: "Ex1: QCM (repro, neuro) | Ex2: Neuro (réflexe)"
        for seg in raw.split("|"):
            m = re.match(r"^\s*Ex\s*(\d+)\s*:\s*(.*)$", seg.strip(), re.I)
            if not m:
                continue
            body = norm(m.group(2))
            if body.upper().startswith("QCM"):
                out.append(row(theme="QCM", type="format", exercice=f"Ex{m.group(1)}", origin=seg.strip()))
                continue
            th = clean_piece(re.sub(r"\s*\(.*?\)", "", body))
            if th:
                out.append(row(theme=th, exercice=f"Ex{m.group(1)}", origin=seg.strip()))
        return _group_by_exercise(out, gid)
    for tok in raw.split(";"):
        m = re.match(r"^\s*(.+?)\s*:\s*EX\s*([\d+]+)\s*$", tok, re.I)
        if not m:
            continue
        th = clean_piece(m.group(1))
        out.append(row(theme=th, type="format" if th.upper() == "QCM" else "theme",
                       exercice=f"Ex{m.group(2)}", origin=norm(tok)))
    return _group_by_exercise(out, gid)


def parse_english(raw: str, gid=None) -> list[dict]:
    """'Essay 1: Women in farming / gender prejudice; Essay 2: Quitting jobs / graph'  or  'Life Issues : Ecodriving (letter)'."""
    out = []
    for tok in raw.split(";"):
        tok = norm(tok)
        fmt = ""
        m = re.match(r"^(Essay\s*\d)\s*:\s*(.+)$", tok)
        if m:
            fmt, tok = m.group(1), m.group(2)
        m = re.match(r"^(.*?)\s*\(letter\)$", tok)
        if m:
            fmt, tok = (fmt + " letter").strip(), m.group(1)
        pieces = [clean_piece(p) for p in tok.split(" / ") if clean_piece(p)]
        kinds = [p for p in pieces if p.lower() in ENGLISH_FORMATS]
        topics = [p for p in pieces if p.lower() not in ENGLISH_FORMATS]
        fmt = (fmt + (" - " + kinds[0] if kinds else "")).strip(" -")
        if not topics:                                  # bare "paragraph", "article"...
            out += [row(theme=k, type="format", format=fmt, origin=raw) for k in kinds]
        for t in topics:
            out.append(row(theme=t, format=fmt, origin=raw))
    return out


# ----------------------------------------------------------------------------- aliases
def load_aliases() -> dict[tuple[str, str], str]:
    if not ALIASES.exists():
        return {}
    a = pd.read_csv(ALIASES, encoding="utf-8-sig").fillna("")
    return {(norm(r["Matière"]), key(r["Variante"])): norm(r["Canonique"]) for _, r in a.iterrows()}


KEEP_CASE = {"Anglais", "Français", "Allemand", "Espagnol", "Italien", "Philosophie (الفلسفة)"}


def _cap(subject: str, t: str) -> str:
    keep = subject in KEEP_CASE or subject.startswith("Arabe") or not t[:1].islower() or t[1:2].isupper()
    return t if keep else t[0].upper() + t[1:]


def canonicalise(df: pd.DataFrame, aliases: dict):
    """1) manual aliases  2) merge spelling/case/accent/punctuation variants automatically.
    Returns (df, resolve) where resolve(subject, name) maps any name to its canonical form."""
    df["theme"] = [aliases.get((s, key(t)), t) for s, t in zip(df["subject"], df["theme"])]
    counts = df.groupby(["subject", "theme"]).size()
    canon: dict[tuple[str, str], str] = {}
    for (subj, th), n in counts.items():
        k = (subj, key(th))
        best = canon.get(k)
        if best is None or (counts[(subj, best)], len(best)) < (n, len(th)):
            canon[k] = th

    def resolve(subject: str, name: str) -> str:
        a = aliases.get((subject, key(name)), name)
        return _cap(subject, canon.get((subject, key(a)), a))

    df["theme"] = [resolve(s, t) for s, t in zip(df["subject"], df["theme"])]
    return df, resolve


HIERARCHY = DATA / "hierarchy.csv"


def load_hierarchy() -> dict[tuple[str, str], str]:
    if not HIERARCHY.exists():
        return {}
    h = pd.read_csv(HIERARCHY, encoding="utf-8-sig").fillna("")
    return {(norm(r["Matière"]), key(r["Thème"])): norm(r["Unité"]) for _, r in h.iterrows()}


def assign_units(df: pd.DataFrame, resolve, hier: dict) -> pd.DataFrame:
    """`Unité` = the parent chapter a theme belongs to, so exam sittings can be compared at chapter level.
       1. hierarchy.csv (your decisions)      2. Anglais 'Unit : Topic' -> Unit
       3. 'Theme (detail)' -> Theme            4. otherwise the theme is its own unit.
       Essay topics (no unit in the programme) get an empty Unité."""
    units = []
    for s, t, f in zip(df["subject"], df["theme"], df["format"]):
        u = hier.get((s, key(t)))
        if u is None:
            if s == "Anglais":
                u = t.split(" : ")[0] if " : " in t else ""
            else:
                m = re.match(r"^(.*?)\s*\(.+\)$", t)
                u = resolve(s, m.group(1)) if m else t
        units.append(u)
    df["unit"] = units
    return df


# ----------------------------------------------------------------------------- main
ANALYSIS_UNITS = {"Fct exp", "Fct ln", "Intégr", "Suite", "Analyse"}


def source_data_issues(raw: pd.DataFrame, df: pd.DataFrame) -> list[dict]:
    """Logical problems in the SOURCE data that cleaning cannot fix: they need the real papers."""
    out = []
    # 1) a sitting missing inside a timeline (e.g. Principale 2008 absent while Contrôle 2008 exists)
    for (b, s), g in raw.groupby(["branch", "subject"]):
        sessions = sorted(g["session"].unique())
        have = set(zip(g["year"], g["session"]))
        for y in range(int(g["year"].min()), int(g["year"].max()) + 1):
            for se in sessions:
                if (y, se) not in have:
                    out.append(dict(branch=b, subject=s, year=y, session=se, tab="",
                                    problem="sitting missing inside the timeline", original=""))
    # 2) Principale and Contrôle with literally the same text (possible copy-paste) - verify against the papers
    x = raw[raw["session"].isin(["Principale", "Contrôle"]) & (raw["subject"] != "SVT (par exercice)")]
    for (b, s, y), g in x.groupby(["branch", "subject", "year"]):
        if len(g) == 2 and g["cell"].nunique() == 1 and len(norm(g["cell"].iloc[0])) > 12:
            out.append(dict(branch=b, subject=s, year=y, session="Principale = Contrôle", tab=int(g["tab"].iloc[0]),
                            problem="identical text in both sessions (verify)", original=norm(g["cell"].iloc[0])))
    # 3) Maths sittings that record no analysis chapter although analysis is part of every exam
    m = df[(df["subject"] == "Mathématiques") & (df["type"] == "theme")]
    for (b, y, se), g in m.groupby(["branch", "year", "session"]):
        if not set(g["unit"]) & ANALYSIS_UNITS:
            out.append(dict(branch=b, subject="Mathématiques", year=y, session=se, tab="",
                            problem="no analysis chapter recorded (source table lists only algebra/geometry)",
                            original="; ".join(g["theme"])))
    return out


def main():
    raw = pd.read_csv(RAW, encoding="utf-8-sig")
    raw.columns = ["branch", "subject", "year", "session", "cell", "tab"]
    counter = iter(range(1, 10**9))
    gid = lambda: f"g{next(counter)}"

    tidy, issues = [], []
    for r in raw.itertuples(index=False):
        base = dict(branch=norm(r.branch), subject=norm(r.subject), year=int(r.year),
                    session=norm(r.session), tab=int(r.tab))
        atoms = parse_cell(base["subject"], r.cell, gid)
        if not atoms:
            issues.append({**base, "problem": "empty / placeholder", "original": norm(r.cell)})
        for a in atoms:
            tidy.append({**base, **a})
    df = pd.DataFrame(tidy)
    df = df[df["theme"].str.len() > 0]
    df, resolve = canonicalise(df, load_aliases())
    df = assign_units(df, resolve, load_hierarchy())
    df = df.drop_duplicates(subset=["branch", "subject", "year", "session", "theme", "type", "exercice", "format"])
    # sittings that list themes but give no unit (e.g. Anglais 2026: essay topics only)
    k4 = ["branch", "subject", "year", "session"]
    no_unit = df[df["type"] == "theme"].groupby(k4).apply(lambda g: (g["unit"] == "").all(), include_groups=False)
    for (b, sj, y, se), flag in no_unit.items():
        if flag:
            issues.append(dict(branch=b, subject=sj, year=y, session=se, tab="", problem="no unit/chapter given",
                               original="; ".join(df[(df.branch == b) & (df.subject == sj) & (df.year == y) & (df.session == se)]["theme"])))

    issues += source_data_issues(raw, df)

    out = df.rename(columns={"branch": "Branche", "subject": "Matière", "year": "Année", "session": "Session",
                             "theme": "Thème", "unit": "Unité", "type": "Type", "format": "Format",
                             "discipline": "Discipline", "exercice": "Exercice", "group": "Groupe",
                             "doc": "Document", "note": "Note", "origin": "Origine", "tab": "Tableau_source"})
    cols = ["Branche", "Matière", "Année", "Session", "Thème", "Unité", "Type", "Format", "Discipline",
            "Exercice", "Groupe", "Document", "Note", "Origine", "Tableau_source"]
    out[cols].to_csv(DATA / "bac_themes_tidy.csv", index=False, encoding="utf-8-sig")

    # wide file for the app: the raw file's 6 columns + `Unités`; duplicate raw rows are collapsed
    k = ["branch", "subject", "year", "session"]
    themes = df[df["type"] == "theme"].groupby(k, sort=False)["theme"].apply(lambda x: "; ".join(dict.fromkeys(x)))
    units = (df[(df["type"] == "theme") & (df["unit"] != "")].groupby(k, sort=False)["unit"]
             .apply(lambda x: "; ".join(dict.fromkeys(x))))
    wide = raw.drop(columns="cell").copy()
    for c in ("branch", "subject", "session"):
        wide[c] = wide[c].map(norm)
    keys = list(zip(wide.branch, wide.subject, wide.year, wide.session))
    wide["cell"] = [themes.get(x, "") for x in keys]
    wide["units"] = [units.get(x, "") for x in keys]
    wide.columns = ["Branche", "Matière", "Année", "Session", "Tableau_source", "Chapitres / Thèmes", "Unités"]
    wide = wide[["Branche", "Matière", "Année", "Session", "Chapitres / Thèmes", "Tableau_source", "Unités"]]
    wide = wide.drop_duplicates()
    wide.to_csv(DATA / "bac_repartition_v2.csv", index=False, encoding="utf-8-sig")

    pd.DataFrame(issues).drop_duplicates().to_csv(DATA / "review_issues.csv", index=False, encoding="utf-8-sig")
    write_review(df)
    print(f"raw rows {len(raw)} -> wide rows {len(wide)}, tidy rows {len(out)}; issues {len(issues)}")


def write_review(df: pd.DataFrame):
    """Pairs inside a subject that are probably one theme: one contains the other, or differ by 1-2 letters."""
    import difflib
    rows = []
    for subj, g in df[df["type"] == "theme"].groupby("subject"):
        vc = g["theme"].value_counts()
        names = list(vc.index)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                ka, kb = key(a), key(b)
                if len(ka) < 3 or len(kb) < 3:
                    continue
                ratio = difflib.SequenceMatcher(None, ka, kb).ratio()
                if ratio >= 0.8 or (len(ka) >= 4 and len(kb) >= 4 and (ka in kb or kb in ka)):
                    rows.append({"Matière": subj, "Thème A": a, "n A": vc[a], "Thème B": b, "n B": vc[b],
                                 "similarité": round(ratio, 2), "Canonique à choisir": ""})
    prop = []
    for subj, g in df[df["type"] == "theme"].groupby("subject"):
        names = sorted(set(g["theme"]), key=len)
        for i, parent in enumerate(names):
            for child in names[i + 1:]:
                if child.lower().startswith(parent.lower() + " ") and (g["unit"][g["theme"] == child] != parent).all():
                    prop.append({"Matière": subj, "Thème": child, "Unité proposée": parent})
    pd.DataFrame(prop).to_csv(DATA / "review_hierarchy.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(rows).sort_values(["Matière", "similarité"], ascending=[True, False]).to_csv(DATA / "review_aliases.csv", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    sys.exit(main())
