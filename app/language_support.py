"""Global caller-language preference and lightweight UI translation support."""
from __future__ import annotations

from html import escape

from fastapi.responses import HTMLResponse


LANGUAGE_SCRIPT = r"""
(function(){
  const KEY = 'metrocrm_caller_speech_language';
  const ALLOWED = ['en', 'hi', 'hinglish'];
  const translations = {
    hi: {
      'Dashboard':'डैशबोर्ड', 'Caller Property Search':'कॉलर प्रॉपर्टी सर्च',
      'Property Data':'प्रॉपर्टी डेटा', 'User Management':'यूज़र मैनेजमेंट',
      'Integrations':'इंटीग्रेशन', 'Visit Alerts':'विज़िट अलर्ट',
      'User Approvals':'यूज़र अप्रूवल', 'Login Approval Requests':'लॉगिन अप्रूवल रिक्वेस्ट',
      'Backup Status':'बैकअप स्टेटस', 'My Profile':'मेरी प्रोफ़ाइल', 'Logout':'लॉगआउट',
      'CRM Workspace':'CRM वर्कस्पेस', 'Secure business management portal':'सुरक्षित बिज़नेस मैनेजमेंट पोर्टल',
      'Language':'भाषा', 'Professional English':'प्रोफेशनल इंग्लिश',
      'Session expires in ':'सेशन समाप्त होगा ', 'Quick Actions':'क्विक एक्शन्स',
      'System Status':'सिस्टम स्टेटस', 'Active':'सक्रिय', 'Online':'ऑनलाइन', 'Live':'लाइव',
      'Connected':'कनेक्टेड', 'Secure session':'सुरक्षित सेशन'
    },
    hinglish: {
      'Dashboard':'Dashboard', 'Caller Property Search':'Caller Property Search',
      'Property Data':'Property Data', 'User Management':'User Management',
      'Integrations':'Integrations', 'Visit Alerts':'Visit Alerts',
      'User Approvals':'User Approvals', 'Login Approval Requests':'Login Approval Requests',
      'Backup Status':'Backup Status', 'My Profile':'My Profile', 'Logout':'Logout',
      'CRM Workspace':'CRM Workspace', 'Secure business management portal':'Secure business management portal',
      'Language':'Bhasha', 'Professional English':'Professional English',
      'Quick Actions':'Quick Actions', 'System Status':'System Status',
      'Active':'Active', 'Online':'Online', 'Live':'Live', 'Connected':'Connected',
      'Secure session':'Secure session'
    }
  };
  const names = {en:'Professional English', hi:'हिंदी', hinglish:'Hindi Meaning · English Letters'};

  function normalize(value){ return ALLOWED.includes(value) ? value : 'en'; }
  function selected(){ return normalize(localStorage.getItem(KEY) || 'en'); }
  function translateText(value, lang){
    if(lang === 'en') return value;
    const map = translations[lang] || {};
    if(Object.prototype.hasOwnProperty.call(map, value)) return map[value];
    return value;
  }
  function apply(lang, announce){
    lang = normalize(lang);
    localStorage.setItem(KEY, lang);
    document.documentElement.lang = lang === 'hi' ? 'hi' : 'en';
    const select = document.getElementById('globalSpeechLanguage');
    if(select) select.value = lang;
    document.querySelectorAll('[data-metrocrm-i18n]').forEach(function(el){
      const source = el.getAttribute('data-metrocrm-i18n');
      if(source) el.textContent = translateText(source, lang);
    });
    document.querySelectorAll('.nav a, .profile-menu a, .page-heading p, .nav-title, .panel h3, .panel-sub, .action strong, .action span').forEach(function(el){
      if(el.closest('.global-language')) return;
      if(!el.dataset.metrocrmOriginal) el.dataset.metrocrmOriginal = el.textContent.trim();
      const original = el.dataset.metrocrmOriginal;
      const translated = translateText(original, lang);
      if(translated !== original && el.children.length === 0) el.textContent = translated;
    });
    const label = document.querySelector('.global-language label');
    if(label) label.textContent = lang === 'hi' ? '🌐 भाषा' : (lang === 'hinglish' ? '🌐 Bhasha' : '🌐 Language');
    const status = document.getElementById('languageStatus');
    if(status && announce){
      status.textContent = '✓ ' + names[lang];
      status.style.display = 'inline';
      clearTimeout(window.__metrocrmLanguageStatusTimer);
      window.__metrocrmLanguageStatusTimer = setTimeout(function(){status.style.display='none';},2500);
    }
    window.dispatchEvent(new CustomEvent('metrocrm:caller-language-change',{detail:{language:lang}}));
    return lang;
  }

  function bind(){
    const select = document.getElementById('globalSpeechLanguage');
    if(select && !select.dataset.metrocrmLanguageBound){
      select.dataset.metrocrmLanguageBound = '1';
      ['change','input'].forEach(function(eventName){
        select.addEventListener(eventName, function(){ apply(select.value, true); });
      });
    }
    apply(selected(), false);
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, {once:true});
  else bind();
  window.addEventListener('pageshow', function(){ apply(selected(), false); });
  window.metrocrmLanguage = {get:selected, set:function(lang){return apply(lang, true);}, names:names};
})();
"""


async def _inject_language_script(request, call_next):
    response = await call_next(request)
    if not isinstance(response, HTMLResponse):
        return response
    body = response.body
    marker = b"</body>"
    if marker not in body or b"window.metrocrmLanguage" in body:
        return response
    script = ("<script>" + LANGUAGE_SCRIPT + "</script>").encode("utf-8")
    response.body = body.replace(marker, script + marker, 1)
    if "content-length" in response.headers:
        del response.headers["content-length"]
    return response


def install_language_support(app) -> None:
    """Install response-level support so every rendered portal page shares one preference."""
    app.middleware("http")(_inject_language_script)
