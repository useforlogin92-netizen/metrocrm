from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_sm_submission_pages_are_standalone_and_not_crm_navigation_shells():
    template_paths = [
        ROOT / "app" / "templates" / "property_submission.html",
        ROOT / "app" / "templates" / "property_submission_success.html",
        ROOT / "app" / "templates" / "property_submission_expired.html",
    ]
    forbidden_navigation = [
        'href="/dashboard"',
        'href="/admin/',
        'href="/super-admin/',
        'href="/auth/logout"',
        "session-countdown",
        "globalSpeechLanguage",
    ]
    for path in template_paths:
        text = path.read_text(encoding="utf-8")
        assert '{% extends "base.html" %}' not in text, path.name
        for marker in forbidden_navigation:
            assert marker not in text, f"{marker} leaked into {path.name}"
        assert '<meta name="robots" content="noindex,nofollow">' in text
        assert "no-store" in text


def test_sm_form_has_only_token_submission_endpoint_and_no_crm_destination():
    form = (ROOT / "app" / "templates" / "property_submission.html").read_text(encoding="utf-8")
    assert '<form method="post" action="/property-submission/{{ token }}"' in form
    assert "/dashboard" not in form
    assert "/admin/" not in form
    assert "/super-admin/" not in form


def test_sm_submission_router_uses_public_template_for_form_success_and_expiry():
    router = (ROOT / "app" / "routers" / "property_submissions.py").read_text(encoding="utf-8")
    assert 'TemplateResponse("property_submission.html"' in router
    assert 'TemplateResponse("property_submission_success.html"' in router
    assert 'TemplateResponse("property_submission_expired.html"' in router
