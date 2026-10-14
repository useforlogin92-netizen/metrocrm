from app.cloud_calling_models import CloudCallLog
from app.routers.cloud_calling import UpdateCall, router


def test_cloud_call_log_has_scoped_references_and_mock_provider_fields():
    columns = CloudCallLog.__table__.columns
    assert "id" in columns
    assert str(columns["id"].type) == "VARCHAR(36)"
    assert "lead_id" in columns
    assert "customer_id" in columns
    assert "agent_user_id" in columns
    assert "call_type" in columns
    assert "status" in columns
    assert "duration_seconds" in columns


def test_call_update_only_accepts_supported_mock_actions():
    assert UpdateCall(action="answer").action == "answer"
    assert UpdateCall(action="hold").action == "hold"
    try:
        UpdateCall(action="dial-provider")
    except Exception:
        pass
    else:
        raise AssertionError("unsupported call action must be rejected")


def test_mock_call_routes_are_registered_without_provider_webhook():
    routes = {(route.path, tuple(sorted(route.methods or []))) for route in router.routes}
    assert ("/caller/api/calls", ("POST",)) in routes
    assert ("/caller/api/calls/{call_id}", ("PATCH",)) in routes
    assert ("/caller/api/calls/incoming", ("POST",)) in routes
    assert not any("webhook" in path for path, _ in routes)
