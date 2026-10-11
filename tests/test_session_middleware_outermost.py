"""Regression coverage for session middleware ordering in the production entrypoint."""

from starlette.middleware.sessions import SessionMiddleware

from app.main_portal import app as production_app


def test_session_middleware_is_outermost_in_production_entrypoint():
    middleware = production_app.user_middleware

    assert middleware, "The production app must register its session middleware."
    assert middleware[0].cls is SessionMiddleware, (
        "SessionMiddleware must be outermost so request.session exists before "
        "session-aware middleware executes."
    )
