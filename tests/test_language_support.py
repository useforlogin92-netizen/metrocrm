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


def test_language_script_is_injected_into_html_response():
    request = SimpleNamespace()

    async def call_next(_request):
        return HTMLResponse("<html><body><h1>Dashboard</h1></body></html>")

    response = asyncio.run(_inject_language_script(request, call_next))
    assert "window.metrocrmLanguage" in response.body.decode("utf-8")
    assert response.body.decode("utf-8").count("window.metrocrmLanguage") == 1
    assert "</body>" in response.body.decode("utf-8")


def test_language_script_does_not_double_inject():
    request = SimpleNamespace()

    async def call_next(_request):
        return HTMLResponse("<html><body><script>window.metrocrmLanguage={};</script></body></html>")

    response = asyncio.run(_inject_language_script(request, call_next))
    assert response.body.decode("utf-8").count("window.metrocrmLanguage") == 1
