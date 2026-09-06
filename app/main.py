from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.database import Base, engine
import app.models  # noqa: F401


app = FastAPI(title="MetroCRM", version="0.1.0")


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/")
def root() -> JSONResponse:
    return JSONResponse({"app": "MetroCRM", "status": "ok", "version": "0.1.0"})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
