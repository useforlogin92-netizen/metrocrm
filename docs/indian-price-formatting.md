# Indian property price formatting
Shared Python formatter: `app.services.property_pricing.format_property_value`.
Caller search UI: `window.MetroCRMFormatPropertyPrice(value)` from `app/static/caller-price-format.js`.

- `25000000` → `2.5 Cr`
- `13000000` → `1.3 Cr`
- `9500000` → `95 Lakh`
- `950000` → `9.5 Lakh`
- `75000` → `₹75,000`

Lakh and crore outputs are rounded to at most two decimal places and trailing zeros are removed. The caller speech generator already uses `format_property_value` for the property's total price.
