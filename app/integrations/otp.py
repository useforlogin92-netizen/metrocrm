"""Provider-neutral OTP delivery contracts.

Actual SMS/email providers are intentionally not hard-coded. Credentials and
sender/template settings belong in .env or a future encrypted admin store.
"""
from __future__ import annotations

from dataclasses import dataclass

@dataclass(slots=True)
class DeliveryResult:
    provider: str
    accepted: bool
    message_id: str | None = None
    error: str | None = None

class OTPDeliveryProvider:
    name = "test"

    def send(self, destination: str, otp: str, *, channel: str) -> DeliveryResult:
        if channel not in {"sms", "email"}:
            return DeliveryResult(self.name, False, error="unsupported_channel")
        if not destination or not otp:
            return DeliveryResult(self.name, False, error="destination_and_otp_required")
        # TEST provider: never sends real messages.
        return DeliveryResult(self.name, True, message_id="TEST-MESSAGE")
