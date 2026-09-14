from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services.backup_devices import is_device_approved, list_devices, register_device, set_device_status


def test_new_backup_device_requires_super_admin_approval():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        device = register_device(db, "device-1", "Office HDD", "E:/MetroCRM-Backups")
        assert device["status"] == "PENDING"
        assert not is_device_approved(db, "device-1")
        assert set_device_status(db, "device-1", "APPROVED", 42)
        assert is_device_approved(db, "device-1")
        assert list_devices(db)[0]["approved_by_id"] == 42
        assert set_device_status(db, "device-1", "REVOKED", 42)
        assert not is_device_approved(db, "device-1")
    finally:
        db.close()
