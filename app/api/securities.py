from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_beta_access
from app.application.stock_search import SecuritySelectionService
from app.core.database import get_db
from app.repositories.catalog import CatalogConflict

router = APIRouter(prefix="/securities", tags=["stock search"])


@router.get("/search")
def search(scope: Literal["catalog", "watchlist", "briefings"], q: str = Query("", max_length=100),
           sort: Literal["relevance", "name_asc", "name_desc", "code_asc"] = "relevance",
           country: Literal["KR", "US"] | None = None, limit: int = Query(30, ge=1, le=100),
           cursor: str | None = Query(None, max_length=512), account=Depends(require_beta_access),
           db: Session = Depends(get_db)):
    try:
        return SecuritySelectionService(db).search(account.id, scope, q, sort, country, limit, cursor)
    except CatalogConflict as exc:
        raise HTTPException(409, str(exc)) from exc
