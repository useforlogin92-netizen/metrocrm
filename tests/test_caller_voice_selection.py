import json
from types import SimpleNamespace

from app.models import AuditEvent, User
from app.routers.caller_speech_settings import DEFAULT_VOICE, VOICE_CATALOG, selected_voice, set_caller_voice


def test_default_voice_is_valid(db_session):
    assert DEFAULT_VOICE in VOICE_CATALOG
    assert selected_voice(db_session) == DEFAULT_VOICE


def test_selected_voice_reads_latest_admin_setting(db_session):
    db_session.add(AuditEvent(actor_user_id=None, action="CALLER_SPEECH_VOICE_SET", entity_type="CallerSpeechVoice", entity_id="coral", details=json.dumps({"voice": "coral"})))
    db_session.commit()
    assert selected_voice(db_session) == "coral"


def test_voice_selection_requires_admin_or_super_admin(db_session):
    manager = User(id=99, username="manager-voice", password_hash="x", role="MANAGER", is_active=True, is_approved=True)
    db_session.add(manager)
    db_session.commit()
    request = SimpleNamespace(session={"user_id": manager.id, "session_version": 1}, headers={"X-CSRF-Token": ""})
    try:
        set_caller_voice({"voice": "marin"}, request, db_session)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 403
    else:
        raise AssertionError("Manager must not change the global caller voice")
