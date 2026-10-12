(() => {
  const CRORE = 10000000, LAKH = 100000;
  function trimDecimal(value) { return Number(value.toFixed(2)).toString(); }
  function parseAmount(value) {
    const raw = String(value ?? "").trim();
    if (!raw) return null;
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
    if (Math.abs(amount) >= CRORE) return `${trimDecimal(Math.abs(amount) / CRORE)} Cr`;
    if (Math.abs(amount) >= LAKH) return `${trimDecimal(Math.abs(amount) / LAKH)} Lakh`;
    return `${amount < 0 ? "-" : ""}₹${Math.round(Math.abs(amount)).toLocaleString("en-IN")}`;
  }
  function normalizeResults() {
    if (!document.body) return;
    document.querySelectorAll(".result").forEach((card) => {
      card.querySelectorAll(".spec").forEach((spec) => {
        const label = spec.querySelector(".spec-label"), value = spec.querySelector(".spec-value");
        if (label && value && label.textContent.trim().toUpperCase() === "PRICE") value.textContent = formatPrice(value.textContent);
      });
      card.querySelectorAll(".talk-points li").forEach((point) => {
        const text = point.textContent.trim();
        if (/^Around\s+₹?\s*[\d,]+(?:\.\d+)?$/i.test(text)) point.textContent = `Around ${formatPrice(text.replace(/^Around\s+/i, ""))}`;
      });
    });
  }
  window.MetroCRMFormatPropertyPrice = formatPrice;
  normalizeResults();
  if (document.body) new MutationObserver(normalizeResults).observe(document.body, { childList: true, subtree: true, characterData: true });
})();
