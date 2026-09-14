from app.catalog_models import CatalogShare
from app.marketing_models import MarketingCampaign, MarketingLandingVisit, MarketingLeadEvent
from app.models import Customer, Lead, User
from app.routers.marketing import _attribution_values, _catalog_payload, _has_active_catalog_share
from starlette.requests import Request


def test_marketing_models_register_and_store(db_session):
    admin = User(username="admin", password_hash="x", role="ADMIN", is_active=True, is_approved=True)
    db_session.add(admin)
    db_session.flush()
    campaign = MarketingCampaign(
        name="Meta 2BHK",
        channel="FACEBOOK",
        status="ACTIVE",
        landing_token="test-public-token",
        landing_title="2BHK Homes",
        utm_source="facebook",
        utm_medium="paid_social",
        utm_campaign="2bhk_sep",
        created_by_id=admin.id,
    )
    db_session.add(campaign)
    db_session.flush()
    customer = Customer(name="Test Customer", mobile="9999999999")
    db_session.add(customer)
    db_session.flush()
    lead = Lead(customer_id=customer.id, source="MARKETING_FACEBOOK", status="NEW")
    db_session.add(lead)
    db_session.flush()
    db_session.add(MarketingLeadEvent(campaign_id=campaign.id, lead_id=lead.id, source="facebook", medium="paid_social", campaign="2bhk_sep", click_id="fb-test"))
    db_session.add(MarketingLandingVisit(campaign_id=campaign.id, visitor_hash="a" * 64, referrer="https://facebook.com", user_agent="test"))
    db_session.commit()

    saved = db_session.get(MarketingCampaign, campaign.id)
    assert saved.status == "ACTIVE"
    assert saved.channel == "FACEBOOK"
    assert db_session.query(MarketingLeadEvent).filter_by(campaign_id=campaign.id).count() == 1
    assert db_session.query(MarketingLandingVisit).filter_by(campaign_id=campaign.id).count() == 1


def test_catalog_share_remains_the_customer_safe_property_source(db_session):
    share = CatalogShare(token_hash="h" * 64, payload_json='{"title":"Safe Property","description":"Public details"}', created_by_id=1, active=True)
    db_session.add(share)
    db_session.flush()
    campaign = MarketingCampaign(name="Safe Share", channel="INSTAGRAM", status="DRAFT", landing_token="safe-token", catalog_share_id=share.id, created_by_id=1)
    db_session.add(campaign)
    db_session.commit()
    assert db_session.get(MarketingCampaign, campaign.id).catalog_share_id == share.id


def test_campaign_activation_requires_active_catalog_share(db_session):
    assert _has_active_catalog_share(db_session, None) is False
    assert _has_active_catalog_share(db_session, 999999) is False
    share = CatalogShare(token_hash="a" * 64, payload_json='{"title":"Safe Property"}', created_by_id=1, active=True)
    db_session.add(share)
    db_session.flush()
    assert _has_active_catalog_share(db_session, share.id) is True
    share.active = False
    db_session.flush()
    assert _has_active_catalog_share(db_session, share.id) is False


def test_attribution_prefers_query_parameters_and_falls_back_to_campaign_defaults(db_session):
    campaign = MarketingCampaign(
        name="Meta Attribution",
        channel="FACEBOOK",
        status="ACTIVE",
        landing_token="attribution-token",
        utm_source="campaign-source",
        utm_medium="campaign-medium",
        utm_campaign="campaign-name",
        created_by_id=1,
    )
    db_session.add(campaign)
    db_session.flush()

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/m/attribution-token",
        "query_string": b"utm_source=facebook&utm_medium=paid_social&utm_campaign=sep_2bhk&utm_content=creative_a&utm_term=2bhk&fbclid=fb-123",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    request = Request(scope)
    attribution = _attribution_values(request, campaign)
    assert attribution == {
        "source": "facebook",
        "medium": "paid_social",
        "campaign": "sep_2bhk",
        "content": "creative_a",
        "term": "2bhk",
        "click_id": "fb-123",
    }

    fallback_request = Request({**scope, "query_string": b""})
    fallback = _attribution_values(fallback_request, campaign)
    assert fallback["source"] == "campaign-source"
    assert fallback["medium"] == "campaign-medium"
    assert fallback["campaign"] == "campaign-name"
    assert fallback["click_id"] is None


def test_catalog_payload_rejects_inactive_or_malformed_shares(db_session):
    assert _catalog_payload(db_session, None) == {}
    active = CatalogShare(token_hash="b" * 64, payload_json='{"title":"Public","internal_note":"secret"}', created_by_id=1, active=True)
    inactive = CatalogShare(token_hash="c" * 64, payload_json='{"title":"Hidden"}', created_by_id=1, active=False)
    malformed = CatalogShare(token_hash="d" * 64, payload_json="not-json", created_by_id=1, active=True)
    db_session.add_all([active, inactive, malformed])
    db_session.flush()
    assert _catalog_payload(db_session, active.id)["title"] == "Public"
    assert _catalog_payload(db_session, active.id)["internal_note"] == "secret"
    assert _catalog_payload(db_session, inactive.id) == {}
    assert _catalog_payload(db_session, malformed.id) == {}
