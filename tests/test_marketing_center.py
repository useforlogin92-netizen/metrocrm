from datetime import datetime

from app.catalog_models import CatalogShare
from app.marketing_models import MarketingCampaign, MarketingLandingVisit, MarketingLeadEvent
from app.models import Customer, Lead, User


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
