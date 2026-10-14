(() => {
  const root = document.getElementById("cloud-dialer");
  if (!root || root.dataset.initialized === "true") return;
  root.dataset.initialized = "true";
  const token = root.dataset.csrf || "";
  let number = "", current = null, seconds = 0, ticker = null, muted = false, held = false;
  const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
  root.innerHTML = `<div class="cloud-dialer"><label for="dial-number">Phone number</label><input class="dialer-display" id="dial-number" type="tel" autocomplete="off" placeholder="Enter number" aria-label="Phone number"><div class="dialpad">${["1","2","3","4","5","6","7","8","9","*","0","#"].map(k=>`<button type="button" data-key="${k}">${k}</button>`).join("")}</div><p class="call-status" id="call-status" aria-live="polite">Ready · Mock mode</p><p class="dialer-muted" id="call-duration">00:00</p><div id="incoming-slot"></div><div class="dialer-actions"><button class="dialer-primary" id="start-call">Call</button><button id="simulate-incoming">Simulate incoming</button><button id="mute-call" disabled>Mute</button><button id="hold-call" disabled>Hold</button><button id="end-call" class="dialer-danger" disabled>End call</button></div><input type="hidden" id="lead-id"><textarea class="call-notes" id="call-notes" maxlength="4000" placeholder="Call notes (saved when ending call)"></textarea><div class="call-history"><strong>Recent calls</strong><ul id="call-history"><li>Loading…</li></ul></div></div>`;
  const $ = id => root.querySelector("#" + id);
  const api = async (url, options={}) => {
    const response = await fetch(url, {...options, credentials:"same-origin", headers:{"Content-Type":"application/json","X-CSRF-Token":token,...(options.headers||{})}});
    const data = await response.json().catch(()=>({detail:"Unexpected server response"}));
    if (!response.ok) throw new Error(data.detail || "Request failed");
    return data;
  };
  const status = value => { $("call-status").textContent = value; };
  const durationText = () => `${String(Math.floor(seconds/60)).padStart(2,"0")}:${String(seconds%60).padStart(2,"0")}`;
  const startTicker = () => { clearInterval(ticker); seconds=0; $("call-duration").textContent=durationText(); ticker=setInterval(()=>{seconds++;$("call-duration").textContent=durationText()},1000); };
  const stopTicker = () => { clearInterval(ticker); ticker=null; };
  const setActive = active => { $("start-call").disabled=active; $("mute-call").disabled=!active; $("hold-call").disabled=!active; $("end-call").disabled=!active; };
  async function refreshHistory() {
    try {
      const data = await api("/caller/api/calls", {method:"GET", headers:{}});
      $("call-history").innerHTML = data.calls.length ? data.calls.slice(0,12).map(c=>`<li><b>${esc(c.phone_number)}</b> — ${esc(c.call_type)} / ${esc(c.status)} · ${esc(c.duration_seconds)} sec</li>`).join("") : "<li>No calls yet</li>";
    } catch { $("call-history").innerHTML="<li>Call history unavailable</li>"; }
  }
  async function startCall(incoming=false) {
    if (current) return;
    const phone = incoming ? "MOCK-INCOMING" : $("dial-number").value.trim();
    if (!phone) { status("Enter a phone number first"); return; }
    try {
      current = incoming ? await api("/caller/api/calls/incoming",{method:"POST",body:"{}"}) : await api("/caller/api/calls",{method:"POST",body:JSON.stringify({phone_number:phone,lead_id:$("lead-id").value ? Number($("lead-id").value):null})});
      status(incoming ? "Incoming call · ringing (mock)" : "Calling " + phone + " · ringing (mock)");
      setActive(true);
      if (incoming) $("incoming-slot").innerHTML='<div class="incoming-call">Mock incoming call <button id="answer-incoming" type="button">Answer</button><button id="reject-incoming" type="button">Decline</button></div>';
      $("answer-incoming")?.addEventListener("click", answerCall);
      $("reject-incoming")?.addEventListener("click", ()=>finishCall("miss"));
      if (!incoming) await answerCall();
      await refreshHistory();
    } catch(e) { current=null; setActive(false); status(e.message); }
  }
  async function answerCall() {
    if (!current) return;
    try { current=await api("/caller/api/calls/"+encodeURIComponent(current.id),{method:"PATCH",body:JSON.stringify({action:"answer"})}); $("incoming-slot").innerHTML=""; status("Connected · mock call"); startTicker(); }
    catch(e) { status(e.message); }
  }
  async function finishCall(action="end") {
    if (!current) return;
    try {
      current=await api("/caller/api/calls/"+encodeURIComponent(current.id),{method:"PATCH",body:JSON.stringify({action,notes:$("call-notes").value})});
      status("Call "+current.status+" · "+current.duration_seconds+" sec");
      current=null; stopTicker(); setActive(false); muted=false; held=false;
      $("mute-call").textContent="Mute"; $("hold-call").textContent="Hold"; $("incoming-slot").innerHTML="";
      await refreshHistory();
    } catch(e) { status(e.message); }
  }
  root.addEventListener("click", e=>{ const key=e.target.closest("[data-key]"); if(key){$("dial-number").value += key.dataset.key; $("dial-number").focus();} });
  $("start-call").addEventListener("click",()=>startCall(false));
  $("simulate-incoming").addEventListener("click",()=>startCall(true));
  $("mute-call").addEventListener("click",()=>{muted=!muted;$("mute-call").textContent=muted?"Unmute":"Mute";status(muted?"Muted · mock call":held?"On hold · mock call":"Connected · mock call");});
  $("hold-call").addEventListener("click",()=>{held=!held;$("hold-call").textContent=held?"Resume":"Hold";status(held?"On hold · mock call":muted?"Muted · mock call":"Connected · mock call");});
  $("end-call").addEventListener("click",()=>finishCall("end"));
  refreshHistory();
  // Click-to-call links from the existing CRM can open this widget with a number and optional lead ID.
  const params = new URLSearchParams(location.search);
  if (params.get("phone")) $("dial-number").value=params.get("phone");
  if (params.get("lead_id")) $("lead-id").value=params.get("lead_id");
})();