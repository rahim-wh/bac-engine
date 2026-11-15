import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..deps import get_store
from ..models import RecordPage
from ..services.data_store import DataStore

router = APIRouter(prefix="/api", tags=["records"])


def _filters(branch: list[str] | None = Query(None), subject: list[str] | None = Query(None),
             session: list[str] | None = Query(None), year_min: int | None = Query(None, ge=1990, le=2100),
             year_max: int | None = Query(None, ge=1990, le=2100), q: str | None = Query(None, max_length=200)):
    if year_min and year_max and year_min > year_max:
        raise HTTPException(400, "year_min must be <= year_max")
    return dict(branches=branch, subjects=subject, sessions=session, year_min=year_min, year_max=year_max, q=q)


@router.get("/meta")
def meta(store: DataStore = Depends(get_store)):
    return store.meta()


@router.get("/records", response_model=RecordPage)
def records(f: dict = Depends(_filters), sort_by: str = "year", order: str = Query("desc", pattern="^(asc|desc)$"),
            page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=500),
            store: DataStore = Depends(get_store)):
    return store.query(sort_by=sort_by, order=order, page=page, page_size=page_size, **f)


@router.get("/records/export")
def export(f: dict = Depends(_filters), store: DataStore = Depends(get_store)):
    """Download the filtered rows as CSV (UTF-8 with BOM so Excel renders Arabic correctly)."""
    sub = store.filter(**f).sort_values(["year", "session_order"], ascending=False)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Branche", "Matière", "Année", "Session", "Chapitres / Thèmes"])
    w.writerows(sub[["branch", "subject", "year", "session", "theme"]].itertuples(index=False))
    data = "\ufeff" + buf.getvalue()
    return StreamingResponse(iter([data]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": 'attachment; filename="bac_export.csv"'})
