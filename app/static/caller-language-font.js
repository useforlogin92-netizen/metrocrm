(() => {
  const KEY = 'metrocrm_caller_speech_language';
  const allowed = new Set(['en', 'hi', 'hinglish']);
  const englishFont = 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
  const hindiFont = '"Noto Sans Devanagari", "Nirmala UI", Mangal, "Arial Unicode MS", sans-serif';
  function apply(language) {
    const lang = allowed.has(language) ? language : 'en';
    if (lang === 'hi' && !document.getElementById('metrocrm-devanagari-font')) {
      const link = document.createElement('link');
      link.id = 'metrocrm-devanagari-font';
      link.rel = 'stylesheet';
      link.href = 'https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;500;600;700;800&display=swap';
      document.head.appendChild(link);
    }
    const font = lang === 'hi' ? hindiFont : englishFont;
    document.documentElement.lang = lang === 'hi' ? 'hi' : 'en';
    document.documentElement.dataset.metrocrmLanguage = lang;
    document.body.dataset.metrocrmLanguage = lang;
    document.body.style.fontFamily = font;
    document.querySelectorAll('button,input,select,textarea,option,label,table,th,td').forEach((el) => { el.style.fontFamily = font; });
  }
  const current = () => { const value = localStorage.getItem(KEY); return allowed.has(value) ? value : 'en'; };
  apply(current());
  window.addEventListener('metrocrm:caller-language-change', (event) => apply(event.detail?.language || current()));
})();
