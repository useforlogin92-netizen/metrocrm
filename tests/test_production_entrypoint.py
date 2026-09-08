from app.main_portal import app


def test_production_entrypoint_registers_accounting_routes():
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/accounting" in paths
    assert "/accounting/journal" in paths
    assert "/accounting/financials" in paths
    assert "/accounting/periods" in paths
    assert "/accounting/export" in paths
