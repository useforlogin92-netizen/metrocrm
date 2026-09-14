"""Production entrypoint that loads the core app and the separated login portals."""
from app import main
from app import portal  # noqa: F401,E402
from app import portal_boundary  # noqa: F401,E402
from app.language_support import install_language_support
from app.session_compat import install_session_compatibility
from app.logout_cookie_hardening import install_logout_cookie_hardening
from app.property_management_ui import install_property_management_ui
from app.routers import recovery_login_link  # noqa: F401,E402
from app.routers.accounting import router as accounting_router
from app.routers.ai_caller import router as ai_caller_router
from app.routers.caller_assistant import router as caller_assistant_router
from app.routers.caller_leads import router as caller_leads_router
from app.routers.health import router as health_router
from app.routers.media_catalog import router as media_catalog_router
from app.routers.password_recovery import router as password_recovery_router
from app.routers.password_reset_requests import router as password_reset_requests_router
from app.routers.property_data import router as property_data_router
from app.routers.property_data_notifications import router as property_data_notifications_router
from app.routers.property_data_super_admin import router as property_data_super_admin_router
from app.routers.property_management_security import router as property_management_security_router
from app.routers.godrej_test_admin import router as godrej_test_admin_router
from app.routers.godrej_test_property_delete import router as godrej_test_property_delete_router
from app.routers.sales_property import router as sales_property_router
from app.routers.whatsapp import router as whatsapp_router
from app.routers.backup_devices import router as backup_devices_router
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = main.app
from app import oauth_compat  # noqa: F401,E402
from app.routers import user_management_compat  # noqa: F401,E402
from app.routers import system_storage  # noqa: F401,E402

install_property_management_ui(app)
install_session_compatibility(app)
install_logout_cookie_hardening(app)
install_language_support(app)
app.include_router(health_router)
app.include_router(accounting_router)
app.include_router(property_data_router)
app.include_router(property_data_notifications_router)
app.include_router(property_data_super_admin_router)
app.include_router(property_management_security_router)
app.include_router(godrej_test_admin_router)
app.include_router(godrej_test_property_delete_router)
app.include_router(media_catalog_router)
app.include_router(sales_property_router)
app.include_router(caller_assistant_router)
app.include_router(caller_leads_router)
app.include_router(ai_caller_router)
app.include_router(password_recovery_router)
app.include_router(password_reset_requests_router)
app.include_router(whatsapp_router)
app.include_router(backup_devices_router)

# Emergency offline foundation. The service worker only provides a safe shell;
# authenticated CRM data is deliberately not cached until encrypted offline
# storage and conflict-aware server synchronization are implemented.
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/offline", response_class=HTMLResponse, include_in_schema=False)
async def emergency_offline_page():
    with open("app/templates/offline.html", "r", encoding="utf-8") as handle:
        return HTMLResponse(handle.read())

@app.get("/metrocrm-sw.js", include_in_schema=False)
async def metrocrm_service_worker():
    with open("app/static/metrocrm-sw.js", "r", encoding="utf-8") as handle:
        return HTMLResponse(handle.read(), media_type="application/javascript")
