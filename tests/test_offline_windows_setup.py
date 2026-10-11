from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OFFLINE = ROOT / "offline" / "windows"


def test_offline_setup_forces_local_safe_defaults():
    setup = (OFFLINE / "SETUP-WINDOWS.ps1").read_text(encoding="utf-8")
    assert "ENVIRONMENT=development" in setup
    assert "DATABASE_URL=sqlite:///./metrocrm.db" in setup
    assert "BACKUP_CLOUD_PROVIDERS=" in setup
    assert "LEAD_INTEGRATIONS_ENABLED=false" in setup
    assert "WHATSAPP_ENABLED=false" in setup
    assert "EMAIL_PROVIDER=test" in setup


def test_offline_runner_binds_only_to_loopback_by_default():
    runner = (OFFLINE / "RUN-METROCRM.bat").read_text(encoding="utf-8")
    assert "--host 127.0.0.1 --port 8000" in runner
    assert "--host 0.0.0.0" not in runner


def test_offline_backup_does_not_copy_real_environment_secrets():
    backup = (OFFLINE / "BACKUP-METROCRM.ps1").read_text(encoding="utf-8")
    assert '("metrocrm.db","uploads","backups")' in backup
    assert 'Copy-Item (Join-Path $root ".env.example")' in backup
    assert 'Copy-Item (Join-Path $root ".env")' not in backup
    assert "finally {" in backup
    assert 'Remove-Item $temp -Recurse -Force' in backup


def test_offline_readme_does_not_claim_live_database_is_migrated():
    readme = (OFFLINE / "README.md").read_text(encoding="utf-8")
    assert "does not magically copy the Render PostgreSQL database" in readme
    assert "restored separately" in readme
