"""Production entrypoint that loads the core app and the separated login portals."""

from app import main
from app import portal  # noqa: F401,E402
from app.routers.accounting import router as accounting_router

app = main.app
app.include_router(accounting_router)
