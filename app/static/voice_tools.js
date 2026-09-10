(function(){
  'use strict';

  const LANGUAGE_KEY = 'metrocrm_caller_speech_language';
  const LANGUAGES = ['en', 'hi', 'hinglish'];
  const speechLocales = { en: 'en-IN', hi: 'hi-IN', hinglish: 'en-IN' };
  let recognition = null;
  let activeInput = null;
  let speaking = false;

  function selectedLanguage(){
    const value = localStorage.getItem(LANGUAGE_KEY);
    return LANGUAGES.includes(value) ? value : 'en';
  }

  function speechLocale(){ return speechLocales[selectedLanguage()] || 'en-IN'; }

  function stopSpeaking(){
    if('speechSynthesis' in window) window.speechSynthesis.cancel();
    speaking = false;
    document.querySelectorAll('.mcrm-tts.is-speaking').forEach(function(button){
      button.classList.remove('is-speaking');
      button.setAttribute('aria-label','Read aloud');
      button.title='Read aloud';
    });
  }

  function readAloud(text, button){
    if(!('speechSynthesis' in window) || !text.trim()) return;
    if(speaking){ stopSpeaking(); return; }
    const utterance = new SpeechSynthesisUtterance(text.trim());
    utterance.lang = speechLocale();
    utterance.rate = 0.95;
    utterance.pitch = 1;
    speaking = true;
    if(button){
      button.classList.add('is-speaking');
      button.setAttribute('aria-label','Stop reading');
      button.title='Stop reading';
    }
    utterance.onend = stopSpeaking;
    utterance.onerror = stopSpeaking;
    window.speechSynthesis.speak(utterance);
  }

  function createButton(className, label, title, symbol){
    const button = document.createElement('button');
    button.type = 'button';
    button.className = className;
    button.setAttribute('aria-label', label);
    button.title = title;
    button.textContent = symbol;
    return button;
  }

  function addTtsButtons(){
    document.querySelectorAll('.speech, [data-read-aloud]').forEach(function(target){
      if(target.querySelector('.mcrm-tts') || target.dataset.voiceEnhanced === '1') return;
      target.dataset.voiceEnhanced = '1';
      target.classList.add('mcrm-readable');
      const button = createButton('mcrm-tts','Read aloud','Read aloud','🔊');
      button.addEventListener('click',function(event){
        event.stopPropagation();
        readAloud(target.textContent || '', button);
      });
      target.appendChild(button);
    });
  }

  function addSttButtons(){
    const selector = 'textarea, input[type="text"], input[type="search"]';
    document.querySelectorAll(selector).forEach(function(input){
      if(input.dataset.voiceInputEnhanced === '1' || input.disabled || input.readOnly) return;
      if(input.closest('.mcrm-voice-input')) return;
      input.dataset.voiceInputEnhanced = '1';
      const wrapper = document.createElement('div');
      wrapper.className = 'mcrm-voice-input';
      input.parentNode.insertBefore(wrapper, input);
      wrapper.appendChild(input);
      const button = createButton('mcrm-stt','Speech to text','Speak to type','🎙');
      wrapper.appendChild(button);
      button.addEventListener('click',function(){
        if(!('SpeechRecognition' in window) && !('webkitSpeechRecognition' in window)){
          window.alert('Speech-to-text is not supported by this browser. Please use a supported browser such as Chrome.');
          return;
        }
        if(recognition && activeInput === input){
          recognition.stop();
          return;
        }
        if(recognition) recognition.stop();
        const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new Recognition();
        activeInput = input;
        recognition.lang = speechLocale();
        recognition.interimResults = true;
        recognition.continuous = false;
        let finalText = '';
        button.classList.add('is-listening');
        button.textContent = '⏹';
        button.title = 'Stop listening';
        recognition.onresult = function(event){
          let interim = '';
          for(let i = event.resultIndex; i < event.results.length; i++){
            const transcript = event.results[i][0].transcript;
            if(event.results[i].isFinal) finalText += transcript;
            else interim += transcript;
          }
          const before = input.value || '';
          const separator = before && !/[\s]$/.test(before) ? ' ' : '';
          input.value = before + separator + (finalText || interim);
          input.dispatchEvent(new Event('input',{bubbles:true}));
          if(finalText){ finalText = ''; }
        };
        recognition.onend = function(){
          recognition = null;
          activeInput = null;
          button.classList.remove('is-listening');
          button.textContent = '🎙';
          button.title = 'Speak to type';
        };
        recognition.onerror = recognition.onend;
        recognition.start();
      });
    });
  }

  function refresh(){
    addTtsButtons();
    addSttButtons();
  }

  const style = document.createElement('style');
  style.textContent = `
    .mcrm-readable{position:relative;padding-right:52px!important}
    .mcrm-tts,.mcrm-stt{font:inherit;display:inline-grid;place-items:center;border:1px solid #cbd5e1;background:#fff;color:#1d4ed8;cursor:pointer;border-radius:7px;width:32px;height:32px;padding:0;box-shadow:0 1px 3px rgba(15,23,42,.08);transition:.15s}
    .mcrm-tts{position:absolute;right:10px;top:10px}
    .mcrm-tts:hover,.mcrm-stt:hover{background:#eff6ff;border-color:#93c5fd}
    .mcrm-tts.is-speaking{background:#dbeafe}
    .mcrm-voice-input{position:relative;width:100%;display:block}
    .mcrm-voice-input > input,.mcrm-voice-input > textarea{padding-right:48px!important;width:100%}
    .mcrm-stt{position:absolute;right:8px;top:50%;transform:translateY(-50%);z-index:2}
    .mcrm-voice-input textarea + .mcrm-stt{top:12px;transform:none}
    .mcrm-stt.is-listening{background:#fee2e2;border-color:#fca5a5;color:#b91c1c}
  `;
  document.head.appendChild(style);

  document.addEventListener('DOMContentLoaded', refresh);
  if(document.readyState !== 'loading') refresh();
  window.addEventListener('metrocrm:caller-language-change',function(){ stopSpeaking(); });
  window.addEventListener('pageshow',function(){ setTimeout(refresh,50); });
})();
