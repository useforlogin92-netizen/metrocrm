import asyncio

from fastapi.responses import HTMLResponse
from types import SimpleNamespace

from app.language_support import LANGUAGE_SCRIPT, _inject_language_script


def test_language_script_persists_and_applies_all_supported_languages():
    assert "metrocrm_caller_speech_language" in LANGUAGE_SCRIPT
    assert "['en', 'hi', 'hinglish']" in LANGUAGE_SCRIPT
    assert "localStorage.setItem(KEY, lang)" in LANGUAGE_SCRIPT
    assert "select.value = lang" in LANGUAGE_SCRIPT
    assert "metrocrm:caller-language-change" in LANGUAGE_SCRIPT
    assert "'Dashboard':'डैशबोर्ड'" in LANGUAGE_SCRIPT
    assert "'Language':'भाषा'" in LANGUAGE_SCRIPT


def test_language_script_is_injected_into_html_response():
    request = SimpleNamespace()

    async def call_next(_request):
        return HTMLResponse("<html><body><h1>Dashboard</h1></body></html>")

    response = asyncio.run(_inject_language_script(request, call_next))
    body = response.body.decode("utf-8")
    assert "window.metrocrmLanguage" in body
    assert 'data-metrocrm-language-support' in body
    assert "'Dashboard':'डैशबोर्ड'" in body
    assert "</body>" in body
    assert "content-length" not in {key.lower() for key in response.headers.keys()}


def test_language_script_does_not_double_inject_its_own_marker():
    request = SimpleNamespace()

    async def call_next(_request):
        return HTMLResponse(
            '<html><body><script data-metrocrm-language-support>'
            'window.metrocrmLanguage={};'
            '</script></body></html>'
        )

    response = asyncio.run(_inject_language_script(request, call_next))
    body = response.body.decode("utf-8")
    assert body.count("data-metrocrm-language-support") == 1


def test_language_support_still_injects_when_base_template_exposes_language_api():
    request = SimpleNamespace()

    async def call_next(_request):
        return HTMLResponse(
            '<html><body><script>window.metrocrmLanguage={get:function(){}};</script>'
            '</body></html>'
        )

    response = asyncio.run(_inject_language_script(request, call_next))
    body = response.body.decode("utf-8")
    assert body.count("data-metrocrm-language-support") == 1
    assert "'Dashboard':'डैशबोर्ड'" in body
