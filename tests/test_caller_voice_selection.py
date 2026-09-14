import json
from types import SimpleNamespace

from app.models import AuditEvent, User
from app.routers.caller_speech_settings import DEFAULT_FEMALE, DEFAULT_MALE, VOICE_CATALOG, selected_voice, selected_voices, set_caller_voice


def test_default_voice_profiles_are_valid(db_session):
    assert DEFAULT_FEMALE in VOICE_CATALOG
    assert DEFAULT_MALE in VOICE_CATALOG
    assert selected_voice(db_session, "female") == DEFAULT_FEMALE
    assert selected_voice(db_session, "male") == DEFAULT_MALE


def test_selected_voice_reads_latest_gender_profile(db_session):
    db_session.add(AuditEvent(actor_user_id=None, action="CALLER_SPEECH_VOICE_SET", entity_type="CallerSpeechVoice", entity_id="female:shimmer", details=json.dumps({"gender": "female", "voice": "shimmer"})))
    db_session.add(AuditEvent(actor_user_id=None, action="CALLER_SPEECH_VOICE_SET", entity_type="CallerSpeechVoice", entity_id="male:echo", details=json.dumps({"gender": "male", "voice": "echo"})))
    db_session.commit()
    assert selected_voices(db_session) == {"female": "shimmer", "male": "echo"}
    assert selected_voice(db_session, "female") == "shimmer"
    assert selected_voice(db_session, "male") == "echo"


def test_voice_selection_requires_admin_or_super_admin(db_session):
    manager = User(id=99, username="manager-voice", password_hash="x", role="MANAGER", is_active=True, is_approved=True)
    db_session.add(manager)
    db_session.commit()
    request = SimpleNamespace(session={"user_id": manager.id, "session_version": 1}, headers={"X-CSRF-Token": ""})
    try:
        set_caller_voice({"gender": "female", "voice": "shimmer"}, request, db_session)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 403
    else:
        raise AssertionError("Manager must not change caller voice profiles")
