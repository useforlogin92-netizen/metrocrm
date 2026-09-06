"""Render a sanitized property catalog for customer-facing views."""
from __future__ import annotations

from html import escape
from typing import Any, Mapping


def _label(key: str) -> str:
    return key.replace("_", " ").strip().title()


def render_customer_catalog(payload: Mapping[str, Any], *, title: str = "Property Details") -> str:
    """Create a self-contained HTML fragment from an already-sanitized payload.

    This renderer intentionally accepts only the output of the sharing service;
    it does not decide which internal fields are safe to expose.
    """
    fields = payload.get("fields") or {}
    media = payload.get("media") or []
    contacts = payload.get("contacts") or {}

    field_html = "".join(
        f'<div class="catalog-field"><span>{escape(_label(str(key)))}</span>'
        f'<strong>{escape(str(value))}</strong></div>'
        for key, value in fields.items()
    )

    media_html = "".join(
        f'<figure class="catalog-media"><a href="{escape(str(item.get("url", "")), quote=True)}">'
        f'{escape(str(item.get("title") or item.get("id") or "Media"))}</a></figure>'
        for item in media
        if item.get("url")
    )

    contact_blocks = []
    for contact_type, data in contacts.items():
        label = _label(str(contact_type))
        details = "".join(
            f'<div><span>{escape(_label(str(key)))}</span>: {escape(str(value))}</div>'
            for key, value in data.items()
        )
        contact_blocks.append(f'<section class="catalog-contact"><h3>{escape(label)}</h3>{details}</section>')

    return f'''<article class="property-catalog" data-catalog="customer">
  <header><h1>{escape(title)}</h1></header>
  <section class="catalog-fields">{field_html}</section>
  <section class="catalog-media">{media_html}</section>
  <section class="catalog-contacts">{"".join(contact_blocks)}</section>
</article>'''
