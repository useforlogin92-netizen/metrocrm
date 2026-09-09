"""Production entrypoint that loads the core app and the separated login portals."""

from app import main
from app import portal  # noqa: F401,E402
from app.routers.accounting import router as accounting_router
from app.routers.property_data import router as property_data_router
from app.routers.sales_property import router as sales_property_router

app = main.app
app.include_router(accounting_router)
app.include_router(property_data_router)
app.include_router(sales_property_router)
