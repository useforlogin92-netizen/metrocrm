"""Security boundary for marketing landing pages backed by catalog shares."""
from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.catalog_models import CatalogShare
from app.database import SessionLocal
from app.crm_plus_models import MarketingCampaign

_MARKETING_PATH = re.compile(r"^/m/([^/]+)(?:/lead)?$")


def _share_is_publicly_available(db: Session, share_id: int | None, now: datetime) -> bool:
    if not share_id:
        return False
    share = db.get(CatalogShare, share_id)
    return bool(share and share.active and (share.expires_at is None or share.expires_at >= now))


def marketing_campaign_has_valid_share(db: Session, campaign: MarketingCampaign, now: datetime) -> bool:
    return _share_is_publicly_available(db, campaign.catalog_share_id, now)


class MarketingShareExpiryMiddleware:
    """Prevent marketing URLs from bypassing CatalogShare expiration."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        match = _MARKETING_PATH.match(path)
        if not match:
            await self.app(scope, receive, send)
            return
        token = match.group(1)
        db = SessionLocal()
        try:
            campaign = db.scalar(
                select(MarketingCampaign).where(
                    MarketingCampaign.landing_token == token,
                    MarketingCampaign.status == "ACTIVE",
                )
            )
            if campaign and not marketing_campaign_has_valid_share(db, campaign, datetime.utcnow()):
                response_start: Message = {
                    "type": "http.response.start",
                    "status": 404,
                    "headers": [(b"content-type", b"application/json")],
                }
                response_body: Message = {
                    "type": "http.response.body",
                    "body": b'{"detail":"campaign_not_found_or_not_active"}',
                    "more_body": False,
                }
                await send(response_start)
                await send(response_body)
                return
        finally:
            db.close()
        await self.app(scope, receive, send)


def install_marketing_share_expiry_guard(app) -> None:
    app.add_middleware(MarketingShareExpiryMiddleware)
