"""Secure external lead intake primitives.

This module deliberately stops at normalization/idempotency. A production
adapter must verify the provider's official webhook signature before calling
it; credentials are never accepted from lead payloads.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from app.integrations.providers import NormalizedLead, normalize_lead


def payload_fingerprint(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def verify_hmac_signature(payload: bytes, signature: str, secret: str) -> bool:
    if not payload or not signature or not secret:
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    supplied = signature.removeprefix("sha256=").strip()
    return hmac.compare_digest(expected, supplied)


def prepare_external_lead(provider: str, payload: dict[str, Any], external_id: str | None = None) -> tuple[NormalizedLead, str]:
    lead = normalize_lead(provider, payload, external_id)
    return lead, payload_fingerprint(payload)
