"""Small, opt-in navigation enhancer for standalone authenticated CRM HTML pages."""

from __future__ import annotations

import re


_NAVIGATION_MARKUP = """<nav class="metrocrm-page-navigation" data-metrocrm-history-nav aria-label="Page navigation">
<a href="/dashboard">Dashboard</a>
<button type="button" data-history-back disabled aria-label="Go back to the previous page">← Back</button>
<button type="button" data-history-forward disabled aria-label="Go forward to the next page">Forward →</button>
</nav>"""

_NAVIGATION_STYLE = """<style>
.metrocrm-page-navigation{display:flex;justify-content:flex-end;align-items:center;gap:8px;flex-wrap:wrap;padding:8px 16px;margin:0 auto;max-width:1320px}
.metrocrm-page-navigation a,.metrocrm-page-navigation button{display:inline-block;border:1px solid #cbd5e1;background:#fff;color:#10213f;text-decoration:none;border-radius:8px;padding:8px 12px;font:inherit;font-size:12px;font-weight:750;cursor:pointer}
.metrocrm-page-navigation a:hover,.metrocrm-page-navigation button:hover:not(:disabled){background:#eff6ff;border-color:#93c5fd}
.metrocrm-page-navigation button:disabled{opacity:.45;cursor:not-allowed;background:#f8fafc;color:#94a3b8}
@media(max-width:700px){.metrocrm-page-navigation{padding:8px 10px}.metrocrm-page-navigation a,.metrocrm-page-navigation button{flex:1;text-align:center}}
</style>"""

_NAVIGATION_SCRIPT = """<script>
(function(){
  const root=document.querySelector('[data-metrocrm-history-nav]');
  if(!root)return;
  const back=root.querySelector('[data-history-back]');
  const forward=root.querySelector('[data-history-forward]');
  function sync(){
    if('navigation' in window && window.navigation){
      back.disabled=!window.navigation.canGoBack;
      forward.disabled=!window.navigation.canGoForward;
      return;
    }
    // Older browsers do not expose forward-entry availability.
    back.disabled=window.history.length<=1;
    forward.disabled=false;
  }
  back.addEventListener('click',function(){
    if(back.disabled)return;
    if('navigation' in window && window.navigation)window.navigation.back();
    else window.history.back();
  });
  forward.addEventListener('click',function(){
    if(forward.disabled)return;
    if('navigation' in window && window.navigation)window.navigation.forward();
    else window.history.forward();
  });
  window.addEventListener('pageshow',sync);
  window.addEventListener('popstate',sync);
  if('navigation' in window && window.navigation){
    window.navigation.addEventListener('currententrychange',sync);
    window.navigation.addEventListener('navigate',sync);
  }
  sync();
})();
</script>"""


def add_history_navigation(document: str) -> str:
    """Add Dashboard and state-aware Back/Forward controls to a standalone HTML page.

    This helper is deliberately opt-in: callers must use it only for authenticated
    CRM pages, never public home/login pages, API responses, or non-HTML content.
    """
    if not isinstance(document, str) or not re.search(r"<body\b", document, re.IGNORECASE):
        return document
    if "data-metrocrm-history-nav" in document:
        return document

    if re.search(r"</head\s*>", document, re.IGNORECASE):
        document = re.sub(r"</head\s*>", _NAVIGATION_STYLE + "</head>", document, count=1, flags=re.IGNORECASE)
    else:
        body_start = re.search(r"<body\b", document, re.IGNORECASE)
        if body_start:
            document = document[:body_start.start()] + _NAVIGATION_STYLE + document[body_start.start():]

    body_match = re.search(r"<body\b[^>]*>", document, re.IGNORECASE)
    if not body_match:
        return document
    document = document[:body_match.end()] + _NAVIGATION_MARKUP + document[body_match.end():]

    if re.search(r"</body\s*>", document, re.IGNORECASE):
        document = re.sub(r"</body\s*>", _NAVIGATION_SCRIPT + "</body>", document, count=1, flags=re.IGNORECASE)
    else:
        document += _NAVIGATION_SCRIPT
    return document
