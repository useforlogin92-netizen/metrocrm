# MetroCRM Integrations

This package is the provider boundary for lead acquisition, OTP delivery and project visitor events.

## Lead sources

`magicbricks`, `99acres`, `housing`, `facebook`, `instagram`, `google`, `meta_ads`, `website`, `whatsapp`, `other`.

Each provider should deliver a webhook/API payload to MetroCRM, where it is normalized to the canonical lead shape. Provider-specific IDs must be retained for idempotency and troubleshooting.

## OTP

SMS and email delivery use a provider-neutral contract. Keep API keys, sender IDs, templates and endpoints in environment/configuration; never commit credentials.

## Visitor alerts

Project/property page events are represented without persisting a raw IP address. A hashed visitor key plus project/property/page/time is sufficient for alerting and cooldown logic.

## Production rule

Only authorized provider APIs/webhooks are supported. Do not scrape portals or bypass provider access controls. Before enabling a provider, configure its official API/webhook credentials and verify the signature/authentication scheme.
