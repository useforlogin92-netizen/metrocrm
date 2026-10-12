(() => {
  const CRORE = 10000000;
  const LAKH = 100000;

  function trimDecimal(value, places = 2) {
    return Number(value.toFixed(places)).toString();
  }

  function parseAmount(value) {
    const raw = String(value ?? "").trim();
    if (!raw) return null;

    // Accept raw rupee amounts and values already expressed in Indian units.
    const normalized = raw.toLowerCase().replace(/₹/g, "").replace(/,/g, "");
    const match = normalized.match(/(-?\d+(?:\.\d+)?)\s*(crores?|cr|lakhs?|lacs?|lac)?/i);
    if (!match) return null;

    const number = Number(match[1]);
    if (!Number.isFinite(number)) return null;
    const unit = (match[2] || "").toLowerCase();
    if (["cr", "crore", "crores"].includes(unit)) return number * CRORE;
    if (["lakh", "lakhs", "lac", "lacs"].includes(unit)) return number * LAKH;
    return number;
  }

  function formatPrice(value) {
    const amount = parseAmount(value);
    if (amount === null) return String(value ?? "").trim();
    if (amount >= CRORE) return `${trimDecimal(amount / CRORE)} Cr`;
    if (amount >= LAKH) return `${trimDecimal(amount / LAKH)} Lakh`;
    if (amount <= -CRORE) return `${trimDecimal(amount / CRORE)} Cr`;
    if (amount <= -LAKH) return `${trimDecimal(Math.abs(amount) / LAKH)} Lakh`;
    return `₹${Math.round(amount).toLocaleString("en-IN")}`;
  }

  function normalizeResults() {
    if (!document.body) return;
    document.querySelectorAll(".result").forEach((card) => {
      card.querySelectorAll(".spec").forEach((spec) => {
        const label = spec.querySelector(".spec-label");
        const value = spec.querySelector(".spec-value");
        if (label && value && label.textContent.trim().toUpperCase() === "PRICE") {
          const formatted = formatPrice(value.textContent);
          if (formatted !== value.textContent) value.textContent = formatted;
        }
      });
      card.querySelectorAll(".talk-points li").forEach((point) => {
        const text = point.textContent.trim();
        if (/^Around\s+₹?\s*[\d,]+(?:\.\d+)?$/i.test(text)) {
          point.textContent = `Around ${formatPrice(text.replace(/^Around\s+/i, ""))}`;
        }
      });
    });
  }

  window.MetroCRMFormatPropertyPrice = formatPrice;
  normalizeResults();
  if (document.body) {
    const observer = new MutationObserver(normalizeResults);
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  }
})();
