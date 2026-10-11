"""Tests for white-label settings validation and production route registration."""
from io import BytesIO

import pytest
from PIL import Image

from app.routers.branding_settings import _validated_logo, router


def _png_bytes(width: int = 64, height: int = 32) -> bytes:
    stream = BytesIO()
    Image.new("RGBA", (width, height), (20, 40, 60, 255)).save(stream, format="PNG")
    return stream.getvalue()


def test_logo_validation_normalizes_supported_image_to_png():
    normalized = _validated_logo(_png_bytes())
    with Image.open(BytesIO(normalized)) as image:
        assert image.format == "PNG"
        assert image.size == (64, 32)


def test_logo_validation_rejects_empty_and_oversized_uploads():
    with pytest.raises(ValueError, match="non-empty image"):
        _validated_logo(b"")
    with pytest.raises(ValueError, match="2 MB"):
        _validated_logo(b"x" * (2 * 1024 * 1024 + 1))


def test_logo_validation_rejects_non_image_content():
    with pytest.raises(ValueError, match="valid supported image"):
        _validated_logo(b"not an image")


def test_branding_router_exposes_admin_settings_and_logo_routes():
    paths = {route.path for route in router.routes}
    assert "" in paths
    assert "/logo" in paths
