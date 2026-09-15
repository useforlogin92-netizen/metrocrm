"""Compatibility aliases for Super Admin property-management navigation.

Some property-management handlers intentionally live under the legacy /admin
namespace. The portal boundary can bridge those handlers to dedicated
Super Admin URLs, but every legacy property link must be registered here so a
Super Admin never falls into the Admin login portal.
"""

from app import portal_boundary


portal_boundary._SUPER_ADMIN_LEGACY_ROUTES = portal_boundary._SUPER_ADMIN_LEGACY_ROUTES + (
    ("/admin/media-catalog", "/super-admin/media-catalog"),
    ("/admin/property-data/whatsapp-import", "/super-admin/property-data/whatsapp-import"),
)
