from app.ui_navigation import add_history_navigation


def test_standalone_page_gets_dashboard_and_state_aware_history_controls():
    source = "<!doctype html><html><head><title>CRM</title></head><body><main>Page</main></body></html>"

    result = add_history_navigation(source)

    assert 'href="/dashboard"' in result
    assert 'data-history-back disabled' in result
    assert 'data-history-forward disabled' in result
    assert "window.navigation.canGoBack" in result
    assert "window.navigation.canGoForward" in result
    assert result.index("<body>") < result.index("data-metrocrm-history-nav") < result.index("<main>")


def test_navigation_injection_is_idempotent():
    source = "<html><head></head><body>Page</body></html>"

    once = add_history_navigation(source)
    twice = add_history_navigation(once)

    assert twice == once
    assert twice.count("data-metrocrm-history-nav") == 1


def test_non_html_or_bodyless_content_is_unchanged():
    for source in ("plain text", "<html><head></head></html>", ""):
        assert add_history_navigation(source) == source
