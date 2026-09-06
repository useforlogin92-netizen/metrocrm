from __future__ import annotations

import json
import secrets

from app.catalog_models import CatalogShare, CatalogShareVisit
from app.routers.catalog_sharing import _token_hash
from app.services.catalog_sharing import build_share_payload


def test_catalog_share_token_is_one_way_hashed():
    token = secrets.token_urlsafe(32)
    digest = _token_hash(token)
    assert len(digest) == 64
    assert digest != token
    assert _token_hash(token) == digest


def test_customer_payload_cannot_include_blocked_fields():
    payload = build_share_payload(
        {"title": "Demo", "price": "1 Cr", "commission_percent": 5, "internal_notes": "secret"},
        selected_fields={"title", "price", "commission_percent", "internal_notes"},
    )
    assert payload["fields"] == {"title": "Demo", "price": "1 Cr"}


def test_persistent_share_models_are_json_serializable():
    share = CatalogShare(token_hash="a" * 64, payload_json=json.dumps({"fields": {}}), created_by_id=1)
    visit = CatalogShareVisit(share_id=1, visitor_key_hash="b" * 64)
    assert share.token_hash.startswith("a")
    assert visit.visitor_key_hash.startswith("b")
