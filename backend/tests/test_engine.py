"""Run with `pytest` (engine/store tests need no web server)."""
from app.services import predictor
from app.services.data_store import DataStore, track_of
from app.services.themes import atomize

store = DataStore()


def test_atomize():
    assert atomize("Suite; Matrice; Graphe") == ["Suite", "Matrice", "Graphe"]
    assert atomize("Chi: 1/Acide 2/Amides | Phy: 1/RC+Elec 2/Nucl") == ["Acide", "Amides", "RC+Elec", "Nucl"]
    assert atomize("(aucun chapitre coché)") == []
    assert atomize("Life Issues : Attitudes") == ["Life Issues : Attitudes"]


def test_filter_and_search():
    all_rows = store.query(page_size=1)["total"]
    assert all_rows >= 1500
    r = store.query(subjects=["Anglais"], sessions=["Principale"], year_min=2020, year_max=2022, page_size=500)
    assert r["total"] > 0 and all(2020 <= x["year"] <= 2022 for x in r["rows"])
    assert store.query(q="zzzzqq")["total"] == 0
    assert store.query(q="   ")["total"] == all_rows            # empty query ignored
    assert store.query(q="ECODRIVING")["total"] == store.query(q="ecodriving")["total"] > 0


def test_predict_shape_and_probabilities():
    sl = store.slots("Bac Mathématiques", "Mathématiques", "exam")
    out = predictor.predict(sl, "Principale", 10)
    assert out["predictions"] and all(0 < p["probability"] <= 0.95 for p in out["predictions"])
    assert out["predictions"][0]["probability"] >= out["predictions"][-1]["probability"]


def test_units_group_english_subthemes():
    th = store.slots("Bac Mathématiques", "Anglais", "exam", "theme")
    un = store.slots("Bac Mathématiques", "Anglais", "exam", "unit")
    assert len(un) <= len(th)          # essay-only sittings have no unit and are skipped
    assert max(len(s["themes"]) for s in un) <= max(len(s["themes"]) for s in th)
    all_units = set().union(*[s["themes"] for s in un])
    assert "Holidaying and Art Shows" in all_units
    assert not any(" : " in u for u in all_units)          # no sub-theme leaks into unit level


def test_predict_empty_history():
    assert predictor.predict([], None)["predictions"] == []


def test_backtest_reports_auc_above_random_on_structured_subject():
    sl = store.slots("Bac Technique", "Physique", "exam")
    bt = predictor.backtest(sl)
    assert bt["folds"] > 0 and bt["metric"] == "AUC" and bt["random"] == 0.5
    assert 0.0 <= bt["model"] <= 1.0
    assert bt["model"] > 0.6          # Technique Physique has stable chapters; measured 0.77 on this data
