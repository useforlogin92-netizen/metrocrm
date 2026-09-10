from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi.responses import JSONResponse

from app.database import get_db

router = APIRouter(tags=["health"])


@router.get("/healthz", include_in_schema=False)
def healthz(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unhealthy"})
