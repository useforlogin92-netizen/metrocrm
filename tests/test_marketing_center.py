from app.catalog_models import CatalogShare
from app.marketing_models import MarketingCampaign, MarketingLandingVisit, MarketingLeadEvent
from app.models import Customer, Lead, User
from app.routers.marketing import _attribution_values, _catalog_payload, _has_active_catalog_share, public_marketing_landing, public_marketing_lead
from fastapi import HTTPException
from starlette.requests import Request


def _request(method="GET", path="/", query_string=b"", headers=None):
    return Request({
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query_string,
        "headers": headers or [],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
        "scheme": "http",
    })


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

    request = _request(
        path="/m/attribution-token",
        query_string=b"utm_source=facebook&utm_medium=paid_social&utm_campaign=sep_2bhk&utm_content=creative_a&utm_term=2bhk&fbclid=fb-123",
    )
    attribution = _attribution_values(request, campaign)
    assert attribution == {
        "source": "facebook",
        "medium": "paid_social",
        "campaign": "sep_2bhk",
        "content": "creative_a",
        "term": "2bhk",
        "click_id": "fb-123",
    }

    fallback_request = _request(path="/m/attribution-token")
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


def test_public_marketing_landing_only_renders_allowlisted_catalog_fields(db_session):
    share = CatalogShare(
        token_hash="e" * 64,
        payload_json='{"title":"Public 2BHK","description":"Customer-safe details","city":"Mumbai","price":"₹1 Cr","internal_note":"SECRET_INTERNAL_NOTE","assigned_staff":"staff@example.com","customer_mobile":"9999999999","media":[{"url":"https://example.com/home.jpg"}]}',
        created_by_id=1,
        active=True,
    )
    db_session.add(share)
    db_session.flush()
    campaign = MarketingCampaign(
        name="Public Safety",
        channel="FACEBOOK",
        status="ACTIVE",
        landing_token="public-safe",
        landing_title="Mumbai Homes",
        catalog_share_id=share.id,
        created_by_id=1,
    )
    db_session.add(campaign)
    db_session.flush()

    response = public_marketing_landing("public-safe", _request(path="/m/public-safe", headers=[(b"user-agent", b"test-browser")]), db_session)
    body = response.body.decode("utf-8")
    assert response.status_code == 200
    assert "Mumbai Homes" in body
    assert "Mumbai" in body
    assert "₹1 Cr" in body
    assert "SECRET_INTERNAL_NOTE" not in body
    assert "staff@example.com" not in body
    assert "9999999999" not in body
    assert db_session.query(MarketingLandingVisit).filter_by(campaign_id=campaign.id).count() == 1


def test_public_marketing_landing_rejects_inactive_campaign(db_session):
    campaign = MarketingCampaign(name="Inactive", channel="FACEBOOK", status="DRAFT", landing_token="inactive-public", created_by_id=1)
    db_session.add(campaign)
    db_session.flush()
    try:
        public_marketing_landing("inactive-public", _request(path="/m/inactive-public"), db_session)
        assert False, "inactive campaign should return HTTP 404"
    except HTTPException as exc:
        assert exc.status_code == 404


def test_public_marketing_lead_creates_crm_lead_and_attribution_event(db_session):
    campaign = MarketingCampaign(
        name="Lead Capture",
        channel="FACEBOOK",
        status="ACTIVE",
        landing_token="lead-test",
        utm_source="campaign-source",
        utm_medium="campaign-medium",
        utm_campaign="campaign-name",
        created_by_id=1,
    )
    db_session.add(campaign)
    db_session.flush()
    request = _request(
        method="POST",
        path="/m/lead-test/lead",
        query_string=b"utm_source=query_source&utm_medium=query_medium&utm_campaign=query_campaign&fbclid=query-click",
    )

    response = public_marketing_lead(
        token="lead-test",
        request=request,
        name=" Lead User ",
        mobile="9999999999",
        email="USER@EXAMPLE.COM",
        message="Need brochure",
        website="",
        utm_source="",
        utm_medium="",
        utm_campaign="",
        utm_content="",
        utm_term="",
        fbclid="",
        gclid="",
        db=db_session,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/m/lead-test?submitted=1"
    customer = db_session.query(Customer).filter_by(mobile="9999999999").one()
    lead = db_session.query(Lead).filter_by(customer_id=customer.id).one()
    event = db_session.query(MarketingLeadEvent).filter_by(lead_id=lead.id).one()
    assert customer.name == "Lead User"
    assert customer.email == "user@example.com"
    assert lead.source == "MARKETING_FACEBOOK"
    assert lead.requirement == "Need brochure"
    assert event.source == "query_source"
    assert event.medium == "query_medium"
    assert event.campaign == "query_campaign"
    assert event.click_id == "query-click"
    assert event.landing_path == "/m/lead-test/lead"


def test_public_marketing_lead_honeypot_does_not_create_lead(db_session):
    campaign = MarketingCampaign(name="Bot Filter", channel="GOOGLE", status="ACTIVE", landing_token="bot-test", created_by_id=1)
    db_session.add(campaign)
    db_session.flush()
    before_customers = db_session.query(Customer).count()
    before_leads = db_session.query(Lead).count()
    before_events = db_session.query(MarketingLeadEvent).count()
    response = public_marketing_lead(
        token="bot-test",
        request=_request(method="POST", path="/m/bot-test/lead"),
        name="Bot",
        mobile="9999999999",
        email="",
        message="",
        website="spam",
        utm_source="",
        utm_medium="",
        utm_campaign="",
        utm_content="",
        utm_term="",
        fbclid="",
        gclid="",
        db=db_session,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/m/bot-test"
    assert db_session.query(Customer).count() == before_customers
    assert db_session.query(Lead).count() == before_leads
    assert db_session.query(MarketingLeadEvent).count() == before_events
