"""Production entrypoint that loads the core app and the separated login portals."""
from app import main
from app import portal  # noqa: F401,E402
from app import portal_boundary  # noqa: F401,E402
from app.session_compat import install_session_compatibility  # noqa: E402
from app.routers import recovery_login_link  # noqa: F401,E402
from app.routers.accounting import router as accounting_router
from app.routers.ai_caller import router as ai_caller_router
from app.routers.caller_assistant import router as caller_assistant_router
from app.routers.caller_leads import router as caller_leads_router
from app.routers.health import router as health_router
from app.routers.password_recovery import router as password_recovery_router
from app.routers.password_reset_requests import router as password_reset_requests_router
from app.routers.property_data import router as property_data_router
from app.routers.sales_property import router as sales_property_router
from app.routers.whatsapp import router as whatsapp_router

app = main.app
install_session_compatibility(app)
app.include_router(health_router)
app.include_router(accounting_router)
app.include_router(property_data_router)
app.include_router(sales_property_router)
app.include_router(caller_assistant_router)
app.include_router(caller_leads_router)
app.include_router(ai_caller_router)
app.include_router(password_recovery_router)
app.include_router(password_reset_requests_router)
app.include_router(whatsapp_router)
