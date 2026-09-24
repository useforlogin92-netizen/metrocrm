# Property Update Standard

MetroCRM accepts property updates through exactly four intake methods:

1. Individual Property Update
2. Bulk Property Update
3. WhatsApp Property Data Update
4. SM Received Data by Secure Link

All four methods must normalize into the same Property Master contract before persistence. No channel may create its own property field names or alternate required-field rules.

## Core fields at launch

### Basic
- Project Name
- Property Type
- Configuration
- Carpet Area
- Possession Date

### Location
- Full Address
- Pincode
- Google Maps Link
- Nearby Connectivity / Landmarks

### Financial
- Base Selling Price (BSP)
- Additional / Government Charges
- Payment Plan
- CP Commission %

### Regulatory / Legal
- RERA Registration Number
- Approved Banks List
- Title Deed Type

### Media / Marketing
- High-resolution Site / Flat Photos
- Floor Plan
- Master Layout
- Project PDF Brochure
- Walkthrough Video Link

### CP / Sales
- RM Contact Info
- Site Visit Timings
- Booking Process

## Required-on-create rule

Only the core listing information is required when creating a new listing:

Project Name, Property Type, Configuration, Possession Date, Full Address, Pincode and BSP.

Optional information remains blank when it was not present in the source. The system must not invent or infer missing values.

## Source metadata

Every successful update records:

- Property ID
- Created Date
- Last Updated Date
- Updated By
- Update Source: INDIVIDUAL / BULK / WHATSAPP / SM_LINK
- Verification Status
- Property Status

## Channel behavior

### Individual
Edit the canonical fields directly and validate before save.

### Bulk
Map spreadsheet headers through the same canonical aliases, validate each row, show row-level errors, and only then commit valid changes.

### WhatsApp
WhatsApp text and attachments are analyzed into a review draft. The reviewer sees the canonical Property Master fields. Approval commits through the same persistence/update engine.

### SM secure link
The secure form writes only canonical fields. Submitted data is reviewed/approved using the same validation and persistence path.

The important rule is: **four intake methods, one Property Master format, one validation path, one persistence path.**
