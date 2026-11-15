"""Complete the master-index taxonomy with what the cleaned dataset knows.

    python scripts/build_taxonomy.py

Inputs : data/taxonomy_from_master_index.csv   (your BAC_TUNISIA_MASTER_INDEX tree, parsed)
         data/bac_themes_tidy.csv              (cleaned dataset)
Outputs: data/taxonomy_complete.csv            one row per chapter (unite) and per detailed theme under it
         data/taxonomy_review.csv              every choice that is a guess or needs your confirmation

Rules: your names win. Data names are mapped onto them (MAP_* below, edit and re-run). Whatever the data has and the
tree does not is ADDED (statut=data_only). Blocks without any data stay 'pending'.
statut: ok = in tree and in data | tree_only = in tree, never seen in data | data_only = added from data | pending = nothing yet
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from collections import OrderedDict, defaultdict
from pathlib import Path

import pandas as pd

D = Path(__file__).resolve().parents[1] / "data"
BRANCH = {"01": "Bac Mathématiques", "02": "Bac Sciences Expérimentales", "03": "Bac Technique",
          "04": "Bac Informatique", "05": "Bac Économie et Gestion", "06": "Bac Lettres"}
SHARED_REF = "Bac Mathématiques"          # the optional languages / common papers are identical in every branch
DATA_SUBJECTS = {"Arabe": ["Arabe"], "Francais": ["Français"], "Anglais": ["Anglais"], "Philosophie": ["Philosophie"],
                 "Mathematiques": ["Mathématiques"], "Sciences Physiques": ["Physique-Chimie", "Physique"],
                 "SVT": ["SVT"], "Technique": ["Génie"], "Allemand": ["Allemand"], "Italien": ["Italien"],
                 "Espagnol": ["Espagnol"]}
COMMON_SPORT = {"Arabe", "Francais", "Anglais", "Philosophie"}   # Sport has no data: reuse the common papers' chapters
MATIERE_FIX = {"Sciences_Physiques": "Sciences Physiques", "SVT / Sciences Biologiques": "SVT"}


def key(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s).lower())
    return re.sub(r"[^\w]+", "", "".join(c for c in s if not unicodedata.combining(c)))


# ---------------------------------------------------------------- mappings: data name -> master-tree chapter (conf: sure|assumed)
def _m(unit, conf, *names):
    return {key(n): (unit, conf) for n in names}


MAP_PC: dict[str, tuple[str, str]] = {}
for d in (
    _m("Circuits RC/RL/RLC", "sure", "RC", "RL", "RLC"),
    _m("Physique nucléaire", "sure", "Nucl", "Nucléaire"), _m("Radioactivité", "sure", "Radioac"),
    _m("Ondes", "sure", "Ondes", "Onde", "Onde son"),
    _m("Effet Franck-Hertz", "sure", "Franck-Hertz"), _m("Résonance", "sure", "Résonance elec", "Résonance méca"),
    _m("Mécanique (forcée et libre)", "sure", "Méca forcé", "Mec forcé", "Méca libre", "Mec libre", "Mécanique"),
    _m("Électricité (forcée et amortie)", "sure", "Elec forcé", "Elec amorti", "Elec non amorti"),
    _m("Électricité (forcée et amortie)", "assumed", "Elec", "RLC forcé", "RLC libre", "LC", "LC entretenu"),
    _m("Filtres", "assumed", "Filtre", "Filtre Actif", "Filtre P-B", "Filtrage"),
    _m("Pile", "sure", "Pile", "Pile Daniel"), _m("Base et dilution", "sure", "Dilution"), _m("Base et dilution", "assumed", "Base"),
    _m("Équilibre chimique", "sure", "Équilibre", "Équilibre chimique"), _m("Équilibre chimique", "assumed", "Loi de modération"),
    _m("Acide", "sure", "Acide", "Acide faible"), _m("Acide", "assumed", "Acide base"),
    _m("Cinétique", "sure", "Cinétique", "Cinétique chimique"),
):
    MAP_PC.update(d)
CHIMIE = {key(x) for x in ["Estérification", "Pile", "Pile Daniel", "Électrolyse", "Base", "Dilution", "Équilibre", "Équilibre chimique",
                           "Loi de modération", "Acide", "Acide faible", "Acide base", "Dosage", "Cinétique", "Cinétique chimique",
                           "Amides", "pH", "Catalyse", "Chimie Organique", "Alcool", "Acide carboxylique", "Conductance",
                           "Modélisation", "Base et dilution"]}
MAP_MATH: dict[str, tuple[str, str]] = {}
for d in (
    _m("Exponentielle", "sure", "Fct exp", "Exp", "Exp gr"), _m("Logarithme népérien", "sure", "Fct ln", "Ln", "Ln gr"),
    _m("Suites", "sure", "Suite", "Suite-int"), _m("Intégration", "sure", "Intégr", "Int"), _m("Statistiques", "sure", "Stat"),
    _m("Équations différentielles", "sure", "Équation différentielle"), _m("Probabilités", "sure", "Proba", "Probabilités"),
    _m("Espace", "sure", "Espace", "Géométrie espace"), _m("Nombres complexes", "sure", "Complexes"),
):
    MAP_MATH.update(d)
MAP_SVT = {key(k): (v, "sure") for k, v in {"Gén Hum": "Gén. Hum", "Gén. Hum": "Gén. Hum", "Repro": "Reprod", "Reprod": "Reprod",
                                            "Neuro": "Neuro", "Immuno": "Immuno", "Gén. Diplo": "Gén. Diplo", "Pr. Art": "Pr. Art",
                                            "Comm. Cell": "Comm. Cell", "Génétique": "Génétique"}.items()}
ABBREV = {key(x) for x in ["Gén. Hum", "Gén. Diplo", "Pr. Art", "Comm. Cell", "Immuno", "Neuro", "Reprod", "Comp", "Auto", "Sync",
                           "UAL", "MAT", "ALI", "PIC", "MCC", "MV", "MVA", "RI", "Cotation fonct", "Transmission de mvt",
                           "Transformation de mvt", "Mec libre", "Mec forcé"]}
TREE_SPELLING = {"Effet Frank-Hertz": "Effet Franck-Hertz"}          # the physicist is James Franck
UNRESOLVED = {key(x) for x in ["Eq", "An", "Ana", "Suite ana prob", "Ln exp gr", "Comp", "Auto", "Sync", "RI", "Libre",
                               "Oscillations libres", "Oscillations forcées"]}   # fragments / ambiguous: need your decision
FAMILY = {  # exam family rules stated in the master index conversation; (verify) = still to confirm
    "Arabe": lambda s: "lettres" if s == "06" else "commun", "Philosophie": lambda s: "lettres" if s == "06" else "commun",
    "Francais": lambda s: {"06": "lettres", "03": "technique"}.get(s, "commun"),
    "Anglais": lambda s: {"06": "lettres", "03": "technique"}.get(s, "commun"),
}


def family(sec: str, mat: str) -> str:
    code = sec[:2]
    if sec == "SHARED":
        return "optionnel"
    if mat in FAMILY:
        return FAMILY[mat](code)
    if mat == "Informatique":
        return "sciexp_technique" if code in ("02", "03") else {"01": "math", "04": "info", "05": "eco", "06": "lettres", "07": "sport"}.get(code, "")
    return {"01": "math", "02": "sciexp", "03": "technique", "04": "info", "05": "eco", "06": "lettres", "07": "sport"}.get(code, "")


def clean_name(n: str) -> tuple[str, str]:
    m = re.match(r"^المحور\s*(\d+)\s*:\s*(.*)$", n)
    return (m.group(2), f"المحور {m.group(1)}") if m else (n, "")


def block_data(sec: str, mat: str, th: pd.DataFrame):
    prefixes = DATA_SUBJECTS.get(mat)
    if not prefixes:
        return None
    branch = SHARED_REF if (sec == "SHARED" or (sec.startswith("07") and mat in COMMON_SPORT)) else BRANCH.get(sec[:2])
    if not branch:
        return None
    g = th[(th["Branche"] == branch) & th["Matière"].str.startswith(tuple(prefixes))]
    return g if len(g) else None


def mapper_for(mat: str):
    return {"Sciences Physiques": MAP_PC, "Mathematiques": MAP_MATH, "SVT": MAP_SVT}.get(mat, {})


def fuzzy_tree(name: str, tree_names: list[str]) -> str | None:
    k = key(name)
    for t in tree_names:
        if key(t) == k or key(re.sub(r"\(hors programme\)", "", t)) == k:
            return t
    best = difflib.get_close_matches(k, [key(t) for t in tree_names], n=1, cutoff=0.9)
    return next((t for t in tree_names if key(t) == best[0]), None) if best else None


def main():
    tree = pd.read_csv(D / "taxonomy_from_master_index.csv", encoding="utf-8-sig").fillna("")
    th = pd.read_csv(D / "bac_themes_tidy.csv", encoding="utf-8-sig").fillna("")
    th = th[th["Type"] == "theme"]
    tree["matiere"] = tree["matiere"].replace(MATIERE_FIX)
    out, review = [], []

    for (sec, cat, mat, var), tg in tree.groupby(["section", "categorie", "matiere", "variante"], sort=False):
        data = block_data(sec, mat, th)
        tree_units = [(r.theme, r.groupe, r.statut) for r in tg.itertuples() if r.theme
                      and not (mat == "Sciences Physiques" and r.theme in ("Physique", "Chimie") and "pending" in r.statut)]
        items: "OrderedDict[str, dict]" = OrderedDict()

        def item(unit, grp, from_tree=False, conf="", note=""):
            k = key(unit) + "|" + grp
            if k not in items:
                items[k] = dict(unit=unit, group=grp, tree=from_tree, themes=defaultdict(set), sit=set(), names=set(),
                                conf=conf, note=note, wording=defaultdict(set))
            return items[k]

        for t, g, st in tree_units:                       # your names first
            if t in TREE_SPELLING:
                review.append(dict(section=sec, matiere=mat, genre="spelling_corrected", donnees=t, vers=TREE_SPELLING[t],
                                   question="Spelling corrected from your tree; OK?"))
                t = TREE_SPELLING[t]
            note = "⚠ wording to verify in master index" if "verify" in st else ""
            if "(hors programme)" in t:
                t, note = re.sub(r"\s*\(hors programme\)", "", t).strip(), (note + " hors programme").strip()
            item(t, g, True, note=note)
        tree_units = [(TREE_SPELLING.get(t, re.sub(r"\s*\(hors programme\)", "", t).strip()), g, st) for t, g, st in tree_units]
        if data is not None:
            mp = mapper_for(mat)
            tnames = [t for t, _, _ in tree_units]
            for r in data.itertuples():
                dname, axis = clean_name(r.Thème)
                uname, _ = clean_name(r.Unité)
                if not uname.strip():                    # 2026 English essay topics: no chapter
                    review.append(dict(section=sec, matiere=mat, genre="essay_topic_without_chapter", donnees=dname, vers="",
                                       question="Essay topic, not a chapter: kept out of the taxonomy"))
                    continue
                hit = mp.get(key(uname)) or mp.get(key(dname))
                conf = hit[1] if hit else "sure"
                ft = None if hit else fuzzy_tree(uname, tnames)
                unit = hit[0] if hit else (ft or uname)
                grp = ""
                if mat == "Sciences Physiques":
                    grp = "Chimie" if (key(dname) in CHIMIE or key(uname) in CHIMIE or key(unit) in CHIMIE) else "Physique"
                if mat == "Technique":
                    grp = r.Matière
                if grp == "" and unit in tnames:          # keep the tree's own group when it has one
                    grp = next((g for t, g, _ in tree_units if t == unit), "")
                it = item(unit, grp, False, conf)
                it["sit"].add((r.Année, r.Session))
                if key(uname) != key(unit):
                    it["names"].add(uname)
                if ft and key(ft) != key(uname):
                    it["wording"][uname].add((r.Année, r.Session))
                it["themes"][dname].add((r.Année, r.Session))
                if axis:
                    it["note"] = axis
                if conf == "assumed":
                    review.append(dict(section=sec, matiere=mat, genre="assumed_mapping", donnees=dname, vers=unit,
                                       question="Is this really the same chapter?"))
                if key(dname) in ABBREV or key(uname) in ABBREV:
                    review.append(dict(section=sec, matiere=mat, genre="abbreviation_to_expand", donnees=dname, vers=unit,
                                       question="Full name of this chapter?"))
                if unit != uname and key(unit) != key(uname) and not hit:
                    review.append(dict(section=sec, matiere=mat, genre="renamed_to_tree_spelling", donnees=uname, vers=unit,
                                       question="Data spelling differs from your tree: which is right?"))
        has_data = data is not None
        if not has_data and not tree_units:                # pending block, keep a marker row
            out.append(dict(section=sec, categorie=cat, matiere=mat, variante=var, famille=family(sec, mat), groupe="",
                            unite="", theme="", noms_dans_les_donnees="", statut="pending", source="master_index",
                            n_seances=0, premiere_annee="", derniere_annee="", actif="", note=""))
            continue
        for it in items.values():
            if not has_data and not it["tree"]:
                continue
            years = sorted({y for y, _ in it["sit"]})
            status = ("ok" if it["sit"] else "tree_only") if it["tree"] else "data_only"
            if it["wording"]:                             # data spelling differs from the tree: trust the papers if seen twice+
                best, bsit = max(it["wording"].items(), key=lambda kv: len(kv[1]))
                if len(bsit) >= 2:
                    review.append(dict(section=sec, matiere=mat, genre="renamed_to_data_wording", donnees=best, vers=it["unit"],
                                       question=f"Tree said '{it['unit']}', data says '{best}' ({len(bsit)} sittings): data wording used"))
                    it["note"] = (it["note"].replace("⚠ wording to verify in master index", "").strip() + f" tree wording was '{it['unit']}'").strip()
                    it["unit"] = best
            elif it["tree"] and "⚠" in it["note"] and it["sit"]:
                it["note"] = "wording confirmed by data"
            if key(it["unit"]) in UNRESOLVED:
                status = "unresolved"
                review.append(dict(section=sec, matiere=mat, genre="unresolved_fragment", donnees=it["unit"], vers="",
                                   question="Abbreviation or ambiguous name: what chapter is this?"))
            if sec.startswith("07") and mat in COMMON_SPORT:
                it["note"] = (it["note"] + " | common paper assumed for Sport (French/English may differ)").strip(" |") if mat in ("Francais", "Anglais") else it["note"]
            if has_data and it["tree"] and not it["sit"]:
                review.append(dict(section=sec, matiere=mat, genre="tree_only_never_in_data", donnees="", vers=it["unit"],
                                   question="In your tree but never seen in the dataset: keep?"))
            out.append(dict(section=sec, categorie=cat, matiere=mat, variante=var, famille=family(sec, mat), groupe=it["group"],
                            unite=it["unit"], theme="", noms_dans_les_donnees=" | ".join(sorted(it["names"] - {it["unit"]})),
                            statut=status, source=("both" if it["tree"] and it["sit"] else "master_index" if it["tree"] else "data"),
                            n_seances=len(it["sit"]), premiere_annee=years[0] if years else "", derniere_annee=years[-1] if years else "",
                            actif=("oui" if years and years[-1] >= 2019 else "non") if years else "", note=it["note"]))
            for tname, sit in sorted(it["themes"].items(), key=lambda kv: -len(kv[1])):
                if key(tname) == key(it["unit"]):
                    continue
                ys = sorted({y for y, _ in sit})
                out.append(dict(section=sec, categorie=cat, matiere=mat, variante=var, famille=family(sec, mat), groupe=it["group"],
                                unite=it["unit"], theme=tname, noms_dans_les_donnees="", statut="data_only", source="data",
                                n_seances=len(sit), premiere_annee=ys[0], derniere_annee=ys[-1], actif="oui" if ys[-1] >= 2019 else "non", note=""))

    df = pd.DataFrame(out)
    for c in ("premiere_annee", "derniere_annee"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    for c in ("note",):
        df[c] = df[c].fillna("")
    df.to_csv(D / "taxonomy_complete.csv", index=False, encoding="utf-8-sig")
    rv = pd.DataFrame(review).drop_duplicates()
    rv = rv[~rv["genre"].isin(["renamed_to_tree_spelling", "essay_topic_without_chapter"])]   # informational, not decisions
    rv.to_csv(D / "taxonomy_review.csv", index=False, encoding="utf-8-sig")
    print(f"taxonomy_complete.csv: {len(df)} rows | taxonomy_review.csv: {len(rv)} items")
    print(df.groupby("statut").size().to_dict())


if __name__ == "__main__":
    main()
