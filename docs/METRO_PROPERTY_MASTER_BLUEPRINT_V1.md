# Metro Property Master Blueprint V1 — Combined Architecture

Status: Implementation branch `feature/metro-property-combined-blueprint-v1`

## Purpose

Metro Property is the property intelligence and property-operations layer. MetroCRM remains the customer/lead/sales CRM. Both use the same canonical property data contract when connected.

## 1. Central rule

One Property Master, four operational intake methods, plus AI Research:

- Individual Property Update
- Bulk Excel Update
- WhatsApp Property Data
- SM Secure Link
- AI Property Research / URL Research

All routes normalize into the same Property Master engine before persistence.

## 2. Core hierarchy

Developer -> Project -> Tower/Wing -> Unit/Inventory

Project-level configuration is stored separately from unit-level inventory.

A project can contain:
- multiple towers/wings
- multiple BHK configurations
- multiple carpet-area variants
- amenities
- media
- nearby locations
- legal and source information

## 3. Configuration pricing contract

Each configuration/area row supports:

- Configuration
- Carpet Area
- Per Square Rate
- Bundle Rate
- Total Price (Including All)
- Negotiation
- Availability
- Source details

Per Square Rate and Bundle Rate are independent first-class values. If Bundle Rate is supplied without Total Price, Bundle Rate may seed Total Price for normalization; the source value remains preserved separately.

## 4. Duplicate protection

Create/import first checks existing Project records using:
- Developer
- Project Name
- City
- Locality
- RERA when supplied

A matching project is updated instead of creating a duplicate. Explicit Property ID still takes precedence for direct updates.

## 5. Partial-update rule

A source update only replaces child collections when that collection is present in the payload. A partial update must not erase existing towers/configurations simply because the source did not send them.

## 6. AI Research

URL/name research should use source priority:

1. Official developer/project website
2. RERA / official regulatory records
3. Official brochure / floor plan / documents
4. Trusted property portals
5. Other public sources

Conflicting values are not silently merged. Primary-source values take precedence and conflicts should remain visible for review.

## 7. WhatsApp flow

Text/image/PDF/video -> extraction/OCR -> review draft -> admin review -> correction -> approval -> Property Master.

WhatsApp data must not bypass review and directly become live property data.

## 8. SM Secure Link flow

Admin creates secure link -> SM submits -> link locks -> Admin review -> Approve OR Request Correction -> same link reopens -> resubmit -> final approval.

After approval the submission link is invalidated.

## 9. Media

Property media should support:
- High-resolution photos
- Floor plan
- Master layout
- Brochure PDF
- Walkthrough video
- Google Maps/location reference

Media should retain source and verification information where available.

## 10. Amenities

Amenities are grouped at project level, including parking, security/safety, fitness, kids/family, sports, club/social, green/outdoor, building/utilities and convenience.

Parking is a project amenity, not a configuration-level field in the canonical Property Master form.

## 11. Audit/source tracking

Important property changes retain:
- first entry
- last updated
- updated by
- update source
- changed fields

Sources include INDIVIDUAL, BULK, WHATSAPP, SM_LINK and AI research.

## 12. Excel contract

The ready-to-upload workbook has separate sheets for:
- Property Master
- Property Configurations
- Property Towers
- Examples / Instructions

Property Configurations explicitly carries Per Square Rate and Bundle Rate so BHK/rate data is not lost during import/export.

## 13. Search / matching

Property search should support:
- Developer
- Project
- Location/locality
- Budget
- BHK
- Carpet Area
- Per Square Rate
- Bundle Rate
- Availability
- RERA
- Possession
- Tower/Wing
- Property Type
- Amenities

## 14. Separation from MetroCRM

Metro Property owns:
- Developer / Project / Tower / Unit / Configuration
- Inventory
- Amenities
- Media
- AI Research
- WhatsApp property intake
- SM property intake
- Property bulk/individual operations

MetroCRM owns:
- Leads
- Customers
- Requirements
- Follow-ups
- Site visits
- Sales pipeline
- Booking / post-sales CRM
- Business reporting

## 15. Implementation order

1. Freeze canonical Property Master contract
2. Freeze configuration pricing
3. Freeze duplicate-safe import/upsert
4. Finalize Individual Update
5. Finalize Excel bulk import/export
6. Finalize WhatsApp review/approval
7. Finalize SM secure-link correction/approval
8. Strengthen AI multi-source research
9. Finalize property search/matching
10. Add company/plugin cloning only after the Property Master contract is stable

This document is the master reference for the combined Metro Property implementation.
