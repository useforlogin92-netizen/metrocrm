(() => {
  const css = `
    .metro-ai-speech-launch{position:fixed;right:24px;bottom:24px;z-index:90;border:0;border-radius:999px;padding:13px 18px;background:#111827;color:#fff;font-weight:850;box-shadow:0 10px 28px rgba(15,23,42,.24);cursor:pointer}
    .metro-ai-speech-launch:hover{transform:translateY(-1px)}
    .metro-ai-speech-panel{position:fixed;right:24px;bottom:82px;width:min(760px,calc(100vw - 32px));max-height:78vh;overflow:auto;background:#fff;border:1px solid #dbe3ef;border-radius:16px;box-shadow:0 24px 70px rgba(15,23,42,.25);z-index:91;padding:20px;display:none}
    .metro-ai-speech-panel.open{display:block}.metro-ai-speech-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.metro-ai-speech-head h3{margin:0;font-size:20px}.metro-ai-speech-controls{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin:14px 0}.metro-ai-speech-controls label{font-size:11px;color:#667085}.metro-ai-speech-controls select{margin-top:5px;width:100%;padding:9px;border:1px solid #ccd4e0;border-radius:8px;background:#fff}.metro-ai-speech-actions{display:flex;gap:8px;flex-wrap:wrap}.metro-ai-speech-actions button{border:1px solid #cbd5e1;background:#fff;color:#174ea6;border-radius:8px;padding:9px 12px;font-weight:800;cursor:pointer}.metro-ai-speech-actions .primary{background:#2563eb;color:#fff;border-color:#2563eb}.metro-ai-speech-actions .voice{background:#07883d;color:#fff;border-color:#07883d}.metro-ai-speech-text{margin-top:14px;padding:16px;border-radius:12px;background:#f8fbff;border:1px solid #dbe7fb;white-space:pre-wrap;line-height:1.7;font-size:15px;min-height:150px}.metro-ai-speech-meta{margin-top:8px;font-size:11px;color:#667085}.metro-ai-speech-status{font-size:12px;color:#475467;margin:8px 0}.metro-ai-speech-close{border:0;background:#f1f5f9;border-radius:8px;padding:7px 10px;cursor:pointer;font-weight:800}@media(max-width:700px){.metro-ai-speech-launch{right:14px;bottom:14px}.metro-ai-speech-panel{right:8px;bottom:70px;width:calc(100vw - 16px)}.metro-ai-speech-controls{grid-template-columns:1fr}}
  `;
  const style = document.createElement('style'); style.textContent = css; document.head.appendChild(style);

  function esc(text){return String(text ?? '').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','\"':'&quot;'}[c]));}
  function current(){try{return Array.isArray(CURRENT_RESULTS)?CURRENT_RESULTS:[]}catch(_){return []}}
  function ensureUI(){
    if(document.getElementById('metroAiSpeechLaunch')) return;
    const launch=document.createElement('button'); launch.id='metroAiSpeechLaunch'; launch.className='metro-ai-speech-launch'; launch.type='button'; launch.textContent='🤖 AI Caller Speech'; launch.title='Create one ready-to-speak script from all searched properties';
    launch.onclick=()=>{document.getElementById('metroAiSpeechPanel').classList.toggle('open'); updateCount();}; document.body.appendChild(launch);
    const panel=document.createElement('section'); panel.id='metroAiSpeechPanel'; panel.className='metro-ai-speech-panel'; panel.innerHTML=`
      <div class="metro-ai-speech-head"><div><h3>🤖 AI Caller Speech</h3><div class="metro-ai-speech-meta" id="metroAiSpeechCount"></div></div><button class="metro-ai-speech-close" type="button" id="metroAiSpeechClose">Close</button></div>
      <div class="metro-ai-speech-controls">
        <label>Speech language<select id="metroAiSpeechLanguage"><option value="hinglish">Hindi + English (Hinglish)</option><option value="hi">Hindi</option><option value="en">Professional English</option></select></label>
        <label>Detail level<select id="metroAiSpeechDetail"><option value="full">Full details</option><option value="summary">Short summary</option></select></label>
        <label>Voice<select id="metroAiSpeechVoice"><option value="female">Indian Female</option><option value="male">Indian Male</option></select></label>
      </div>
      <div class="metro-ai-speech-actions"><button class="primary" type="button" id="metroAiSpeechGenerate">✨ Generate Ready Speech</button><button class="voice" type="button" id="metroAiSpeechSpeak">▶ Speak</button><button type="button" id="metroAiSpeechStop">■ Stop</button><button type="button" id="metroAiSpeechCopy">▣ Copy</button></div>
      <div class="metro-ai-speech-status" id="metroAiSpeechStatus">Search properties first, then generate one combined caller script. Properties are grouped by location.</div>
      <div class="metro-ai-speech-text" id="metroAiSpeechText">Ready.</div>`;
    document.body.appendChild(panel);
    document.getElementById('metroAiSpeechClose').onclick=()=>panel.classList.remove('open');
    document.getElementById('metroAiSpeechGenerate').onclick=generate;
    document.getElementById('metroAiSpeechSpeak').onclick=speak;
    document.getElementById('metroAiSpeechStop').onclick=stopSpeech;
    document.getElementById('metroAiSpeechCopy').onclick=copySpeech;
    updateCount();
  }
  function updateCount(){const el=document.getElementById('metroAiSpeechCount');if(el)el.textContent=`${current().length} searched properties • grouped automatically by location`}
  function setStatus(text){const el=document.getElementById('metroAiSpeechStatus');if(el)el.textContent=text}
  async function generate(){
    const properties=current();
    if(!properties.length){setStatus('Pehle property search karke results lao.');document.getElementById('metroAiSpeechText').textContent='No searched properties available.';return}
    setStatus('AI script prepare kar raha hai...');
    try{
      const r=await fetch('/caller/ai-speech/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({properties,language:document.getElementById('metroAiSpeechLanguage').value,detail:document.getElementById('metroAiSpeechDetail').value})});
      const d=await r.json(); if(!r.ok) throw new Error(d.detail||'Generation failed');
      document.getElementById('metroAiSpeechText').textContent=d.text||'No speech generated.';
      setStatus(`${d.ai_used?'AI generated':'CRM-safe fallback generated'} • ${d.count} properties • ${d.group_count} locations`);
    }catch(e){setStatus(`Speech generation failed: ${e.message}`)}
  }
  async function speak(){
    const text=document.getElementById('metroAiSpeechText')?.textContent||''; if(!text||text==='Ready.')return;
    const gender=document.getElementById('metroAiSpeechVoice').value; const language=document.getElementById('metroAiSpeechLanguage').value;
    setStatus('Voice prepare ho rahi hai...');
    try{
      const r=await fetch('/caller/ai-speech/tts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,gender,language})});
      if(r.ok){const blob=await r.blob(); if(window.__metroAiAudio){window.__metroAiAudio.pause();window.__metroAiAudio=null} const audio=new Audio(URL.createObjectURL(blob)); window.__metroAiAudio=audio; audio.onended=()=>setStatus('Speech complete.'); await audio.play(); setStatus(`${gender==='female'?'Indian Female':'Indian Male'} AI voice playing...`); return;}
    }catch(_){/* browser fallback below */}
    if('speechSynthesis' in window){speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(text);u.lang=language==='hi'?'hi-IN':'en-IN';const voices=speechSynthesis.getVoices();const indian=voices.filter(v=>/^en-IN|^hi-IN/i.test(v.lang));const wanted=indian.find(v=>gender==='female'?/female|zira|heera|kalpana|lekha|sangeeta/i.test(v.name):/male|ravi|hemant|prabhat|aditya/i.test(v.name));if(wanted)u.voice=wanted;u.rate=.95;u.pitch=gender==='female'?1.05:.95;u.onend=()=>setStatus('Speech complete.');speechSynthesis.speak(u);setStatus('Browser Indian voice playing. AI voice API is not configured yet.');}
    else setStatus('Voice playback is not supported in this browser.');
  }
  function stopSpeech(){if(window.__metroAiAudio){window.__metroAiAudio.pause();window.__metroAiAudio=null}if('speechSynthesis' in window)speechSynthesis.cancel();setStatus('Speech stopped.')}
  async function copySpeech(){const text=document.getElementById('metroAiSpeechText')?.textContent||'';if(!text||text==='Ready.')return;try{await navigator.clipboard.writeText(text);setStatus('Speech copied.')}catch(_){setStatus('Copy not available.')}}
  function watchResults(){ensureUI();updateCount();}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',watchResults);else watchResults();
  setInterval(updateCount,1200);
})();
