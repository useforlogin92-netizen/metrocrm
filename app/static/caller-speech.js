(() => {
  const KEY = 'metrocrm_caller_speech_language';
  const allowed = new Set(['en', 'hi', 'hinglish']);
  const englishFont = 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
  const hindiFont = '"Noto Sans Devanagari", "Nirmala UI", Mangal, "Arial Unicode MS", sans-serif';
  function apply(language) {
    const lang = allowed.has(language) ? language : 'en';
    if (lang === 'hi' && !document.getElementById('metrocrm-devanagari-font')) {
      const link = document.createElement('link'); link.id = 'metrocrm-devanagari-font'; link.rel = 'stylesheet';
      link.href = 'https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;500;600;700;800&display=swap';
      document.head.appendChild(link);
    }
    const font = lang === 'hi' ? hindiFont : englishFont;
    document.documentElement.lang = lang === 'hi' ? 'hi' : 'en';
    document.documentElement.dataset.metrocrmLanguage = lang;
    document.body.dataset.metrocrmLanguage = lang;
    document.body.style.fontFamily = font;
    document.querySelectorAll('body *').forEach((el) => { el.style.fontFamily = font; });
  }
  const current = () => { const value = localStorage.getItem(KEY); return allowed.has(value) ? value : 'en'; };
  apply(current());
  window.addEventListener('metrocrm:caller-language-change', (event) => apply(event.detail?.language || current()));

  // Always forward the visible Multiple Preferred Locations field to the
  // caller-search API so an unrelated locality cannot leak into results.
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    try {
      const url = typeof input === 'string' ? input : input?.url || '';
      if (url.includes('/caller/search') && init?.body && typeof init.body === 'string') {
        const body = JSON.parse(init.body);
        const locationInput = document.getElementById('locations');
        const typed = locationInput ? locationInput.value.trim() : '';
        const locations = typed ? typed.split(',').map(v => v.trim()).filter(Boolean) : [];
        if (locations.length) body.preferred_locations = locations;
        else if (!Array.isArray(body.preferred_locations)) body.preferred_locations = [];
        init = { ...init, body: JSON.stringify(body) };
      }
    } catch (_) {}
    return nativeFetch(input, init);
  };

  function load(src) { const script = document.createElement('script'); script.src = src; script.async = false; document.body.appendChild(script); }
  load('/static/caller-language-font.js?v=3');
  load('/static/caller-speech-core.js?v=3');
  load('/static/caller-price-format.js?v=1');
})();
