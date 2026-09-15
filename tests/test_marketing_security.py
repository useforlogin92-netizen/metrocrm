from datetime import datetime, timedelta
from types import SimpleNamespace

from app.marketing_security import marketing_campaign_has_valid_share


def test_marketing_campaign_rejects_expired_catalog_share():
    now = datetime(2026, 9, 15, 12, 0, 0)
    share = SimpleNamespace(active=True, expires_at=now - timedelta(seconds=1))
    campaign = SimpleNamespace(catalog_share_id=1)

    class DB:
        def get(self, model, ident):
            return share

    assert marketing_campaign_has_valid_share(DB(), campaign, now) is False


def test_marketing_campaign_accepts_unexpired_catalog_share():
    now = datetime(2026, 9, 15, 12, 0, 0)
    share = SimpleNamespace(active=True, expires_at=now + timedelta(seconds=1))
    campaign = SimpleNamespace(catalog_share_id=1)

    class DB:
        def get(self, model, ident):
            return share

    assert marketing_campaign_has_valid_share(DB(), campaign, now) is True


def test_marketing_campaign_accepts_non_expiring_active_share():
    now = datetime(2026, 9, 15, 12, 0, 0)
    share = SimpleNamespace(active=True, expires_at=None)
    campaign = SimpleNamespace(catalog_share_id=1)

    class DB:
        def get(self, model, ident):
            return share

    assert marketing_campaign_has_valid_share(DB(), campaign, now) is True
