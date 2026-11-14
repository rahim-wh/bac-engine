# Tunisian Bac Analytics & Prediction Engine

```
bac-engine/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app, CORS, startup load
│   │   ├── deps.py                # dataset singleton
│   │   ├── models.py              # Pydantic response models
│   │   ├── routers/records.py     # /api/meta, /api/records, /api/records/export
│   │   ├── routers/analytics.py   # /api/predict, /api/insights/*
│   │   └── services/
│   │       ├── themes.py          # splits composite cells into atomic themes
│   │       ├── data_store.py      # in-memory pandas store, filter/search/sort/slots
│   │       ├── predictor.py       # scoring engine + walk-forward backtest
│   │       └── insights.py        # chart aggregations
│   ├── data/bac_repartition_chapitres_clean.csv
│   ├── tests/test_engine.py
│   └── requirements.txt
└── frontend/  (Vite + React + Tailwind + Recharts + lucide-react)
    └── src/{App.jsx, components/{DataTable,Predictor,Dashboard}.jsx, lib/{api,hooks}.js}
```

## Run
```bash
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && uvicorn app.main:app --reload   # http://127.0.0.1:8000/docs
cd ../frontend && npm install && npm run dev                        # http://localhost:5173
```

## Cleaning the dataset
The raw CSV is never edited. Run `python scripts/clean_csv.py` (from `backend/`) to regenerate:

| File | Purpose |
|---|---|
| `data/bac_themes_tidy.csv` | one row per atomic theme, with `Type` (theme/format), `Exercice`, `Groupe` (themes written together = combinations), `Document`, `Discipline`, `Origine` |
| `data/bac_repartition_v2.csv` | same 6 columns as the raw file, canonical themes joined by `; ` — **the file the app loads** |
| `data/aliases.csv` | **your decisions**: `Matière, Variante, Canonique`. Edit, re-run the script |
| `data/review_aliases.csv` | pairs that may be the same theme (noisy: confirm before merging) |
| `data/review_issues.csv` | exam cells that are empty/unknown: fill from the real papers |

### Units (parent chapters)
`Unité` groups detailed themes under their chapter, so prediction counts the chapter whenever any of its sub-themes appears
(e.g. every `Holidaying and Art Shows : …` topic counts as `Holidaying and Art Shows`). Sources, in order: `data/hierarchy.csv`
(your decisions) → English `Unit : Topic` → `Theme (detail)` → the theme itself. The Predictor and Insights tabs have a **Level** switch.

### Checking the data after any edit
```bash
cd backend
python scripts/clean_csv.py     # rebuild tidy + app files from the raw file, aliases.csv and hierarchy.csv
python scripts/audit_data.py    # 25 logical checks (PASS/FAIL) + warnings, writes data/audit_report.txt
python -m pytest -q tests       # includes the same invariants
```
Row-level problems that only the real exam papers can settle are listed in `data/review_issues.csv`.
