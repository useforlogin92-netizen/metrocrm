"""Local-only mock telephony endpoint for testing the caller workflow.

Enable explicitly in a local environment with METROCRM_ENABLE_MOCK_TELEPHONY=1.
This endpoint never places a real call and must remain disabled in production.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/telephony", tags=["mock-telephony"])


class MockCallRequest(BaseModel):
    executive_id: str = Field(min_length=1, max_length=100)
    client_phone: str = Field(min_length=7, max_length=24)
    lead_name: str = Field(min_length=1, max_length=200)

    @field_validator("executive_id", "lead_name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("client_phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[+()0-9.\-\s]{7,24}", value):
            raise ValueError("client_phone must contain only phone-number characters")
        digits = re.sub(r"\D", "", value)
        if not 7 <= len(digits) <= 15:
            raise ValueError("client_phone must contain 7 to 15 digits")
        return value


class MockCallResponse(BaseModel):
    success: bool
    mock: bool
    call_sid: str
    status: str
    executive_id: str
    lead_name: str
    client_phone_masked: str
    created_at: str
    message: str


def _mask_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if len(digits) <= 4:
        return "*" * len(digits)
    return f"{digits[:2]}{'*' * max(5, len(digits) - 4)}{digits[-2:]}"


@router.post("/mock-call", response_model=MockCallResponse)
def create_mock_call(payload: MockCallRequest) -> MockCallResponse:
    # Hard opt-in keeps the simulator off by default, including on production.
    if os.getenv("METROCRM_ENABLE_MOCK_TELEPHONY", "").strip().lower() not in {"1", "true", "yes"}:
        raise HTTPException(status_code=404, detail="Mock telephony is disabled")

    call_sid = f"MOCK-{uuid.uuid4().hex[:16].upper()}"
    created_at = datetime.now(timezone.utc).isoformat()
    masked_phone = _mask_phone(payload.client_phone)
    logger.info(
        "Mock call initiated sid=%s executive_id=%s lead_name=%r phone=%s",
        call_sid,
        payload.executive_id,
        payload.lead_name,
        masked_phone,
    )
    return MockCallResponse(
        success=True,
        mock=True,
        call_sid=call_sid,
        status="simulated",
        executive_id=payload.executive_id,
        lead_name=payload.lead_name,
        client_phone_masked=masked_phone,
        created_at=created_at,
        message="Mock call accepted. No real telephone call was placed.",
    )
