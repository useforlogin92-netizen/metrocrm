(() => {
  function formatPrice(value) {
    const raw = String(value ?? '').trim();
    if (!raw) return raw;
    const match = raw.match(/₹?\s*([\d,]+(?:\.\d+)?)/);
    if (!match) return raw;
    const amount = Number(match[1].replace(/,/g, ''));
    if (!Number.isFinite(amount)) return raw;
    if (amount >= 10000000) return `${(amount / 10000000).toFixed(2)} Cr`;
    if (amount >= 100000) {
      const lakh = amount / 100000;
      return `${Number(lakh.toFixed(2))} lakh`;
    }
    return `₹${Math.round(amount).toLocaleString('en-IN')}`;
  }

  function normalizeResults() {
    document.querySelectorAll('.result').forEach((card) => {
      card.querySelectorAll('.spec').forEach((spec) => {
        const label = spec.querySelector('.spec-label');
        const value = spec.querySelector('.spec-value');
        if (label && value && label.textContent.trim().toUpperCase() === 'PRICE') {
          const formatted = formatPrice(value.textContent);
          if (formatted !== value.textContent) value.textContent = formatted;
        }
      });
      card.querySelectorAll('.talk-points li').forEach((point) => {
        const text = point.textContent.trim();
        if (/^Around\s+₹?\s*[\d,]+(?:\.\d+)?$/i.test(text)) {
          point.textContent = `Around ${formatPrice(text.replace(/^Around\s+/i, ''))}`;
        }
      });
    });
  }

  window.MetroCRMFormatPropertyPrice = formatPrice;
  normalizeResults();
  const observer = new MutationObserver(normalizeResults);
  observer.observe(document.body, { childList: true, subtree: true, characterData: true });
})();
