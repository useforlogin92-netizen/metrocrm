"""Inline WhatsApp property capture UI for the Property Data workspace."""
from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class WhatsAppPropertyImportUIMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope.get("type") != "http" or path not in {"/admin/property-data", "/super-admin/property-data"}:
            await self.app(scope, receive, send)
            return
        started: Message | None = None
        chunks: list[bytes] = []

        async def capture(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = message
                return
            if message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))
                if message.get("more_body", False):
                    return
                if started is None:
                    await send(message)
                    return
                headers = list(started.get("headers", []))
                content_type = next((v.lower() for k, v in headers if k.lower() == b"content-type"), b"")
                body = b"".join(chunks)
                if b"text/html" not in content_type:
                    await send(started)
                    await send(message)
                    return
                html = body.decode("utf-8", errors="replace")
                if "metrocrm-whatsapp-property-import" not in html:
                    base = "/super-admin/property-data" if path.startswith("/super-admin/") else "/admin/property-data"
                    analyze = f"{base}/whatsapp-import/analyze"
                    widget = f"""
<style>
#metrocrm-whatsapp-modal{{display:none;position:fixed;inset:0;z-index:9999;background:rgba(15,23,42,.55);padding:24px;box-sizing:border-box;align-items:center;justify-content:center}}
#metrocrm-whatsapp-modal.open{{display:flex}}
.metrocrm-wa-card{{width:min(760px,100%);max-height:90vh;overflow:auto;background:#fff;border-radius:16px;padding:22px;box-shadow:0 20px 60px rgba(15,23,42,.25);box-sizing:border-box}}
.metrocrm-wa-card h2{{margin:0 0 6px;font-size:20px;color:#10213f}}
.metrocrm-wa-muted{{font-size:12px;line-height:1.55;color:#64748b}}
.metrocrm-wa-card textarea{{width:100%;min-height:300px;box-sizing:border-box;border:1px solid #cbd5e1;border-radius:10px;padding:12px;font:inherit;resize:vertical}}
.metrocrm-wa-card input[type=file]{{display:block;width:100%;box-sizing:border-box;margin:8px 0;padding:10px;border:1px solid #cbd5e1;border-radius:10px;background:#fff}}
.metrocrm-wa-actions{{display:flex;justify-content:flex-end;gap:10px;flex-wrap:wrap;margin-top:14px}}
.metrocrm-wa-btn{{border:0;border-radius:9px;padding:10px 15px;font:inherit;font-weight:800;cursor:pointer}}
.metrocrm-wa-primary{{background:#2563eb;color:#fff}}
.metrocrm-wa-secondary{{background:#f8fafc;color:#334155;border:1px solid #cbd5e1}}
.metrocrm-wa-primary:disabled{{opacity:.55;cursor:not-allowed}}
</style>
<div id="metrocrm-whatsapp-modal" role="dialog" aria-modal="true" aria-labelledby="metrocrm-whatsapp-title">
  <div class="metrocrm-wa-card">
    <h2 id="metrocrm-whatsapp-title">📲 Property Data Received by WhatsApp</h2>
    <p class="metrocrm-wa-muted">Paste the complete WhatsApp property message below. You can also attach the brochure, PDF, images or videos you received. MetroCRM will extract only information actually present in these sources; anything not present stays blank for later SM verification.</p>
    <form id="metrocrm-whatsapp-form" method="post" action="{analyze}" enctype="multipart/form-data">
      <input type="hidden" name="csrf_token" id="metrocrm-whatsapp-csrf" value="{csrf_token}">
      <label for="metrocrm-whatsapp-text"><b>WhatsApp message</b></label>
      <textarea id="metrocrm-whatsapp-text" name="source_text" placeholder="Paste WhatsApp text here..." required></textarea>
      <label for="metrocrm-whatsapp-files" style="display:block;margin-top:12px"><b>Attachments</b></label>
      <input id="metrocrm-whatsapp-files" type="file" name="files" multiple accept=".jpg,.jpeg,.png,.webp,.pdf,.mp4,.mov">
      <div class="metrocrm-wa-muted">Allowed: PDF, JPG, PNG, WEBP, MP4, MOV · up to 30 MB per attachment.</div>
      <div class="metrocrm-wa-actions">
        <button type="button" id="metrocrm-whatsapp-cancel" class="metrocrm-wa-btn metrocrm-wa-secondary">Cancel</button>
        <button type="submit" id="metrocrm-whatsapp-submit" class="metrocrm-wa-btn metrocrm-wa-primary">🤖 Analyze &amp; Create Review Draft</button>
      </div>
    </form>
  </div>
</div>
<script>
(function(){{
  const modal=document.getElementById('metrocrm-whatsapp-modal');
  const form=document.getElementById('metrocrm-whatsapp-form');
  const text=document.getElementById('metrocrm-whatsapp-text');
  const csrf=document.getElementById('metrocrm-whatsapp-csrf');
  const submit=document.getElementById('metrocrm-whatsapp-submit');
  const cancel=document.getElementById('metrocrm-whatsapp-cancel');
  const sourceToken=document.querySelector('input[name="csrf_token"]');
  const open=function(e){{if(e)e.preventDefault();if(sourceToken)csrf.value=sourceToken.value;modal.classList.add('open');setTimeout(function(){{text.focus();}},0);}};
  const close=function(){{modal.classList.remove('open');}};
  const trigger=document.getElementById('metrocrm-whatsapp-property-import');
  if(trigger) trigger.addEventListener('click',open);
  if(cancel) cancel.addEventListener('click',close);
  modal.addEventListener('click',function(e){{if(e.target===modal)close();}});
  document.addEventListener('keydown',function(e){{if(e.key==='Escape' && modal.classList.contains('open'))close();}});
  form.addEventListener('submit',function(){{submit.disabled=true;submit.textContent='Analyzing…';}});
}})();
</script>
"""
                    link = '<button id="metrocrm-whatsapp-property-import" class="pd-btn primary" type="button">📲 Property Data Received by WhatsApp</button>'
                    html = html.replace('<a class="pd-btn" href="/admin/media-catalog">🖼 Property Media Catalog</a>', '<a class="pd-btn" href="/admin/media-catalog">🖼 Property Media Catalog</a>' + link + widget, 1)
                encoded = html.encode("utf-8")
                headers = [(k, v) for k, v in headers if k.lower() != b"content-length"]
                headers.append((b"content-length", str(len(encoded)).encode("ascii")))
                start = dict(started)
                start["headers"] = headers
                await send(start)
                await send({"type": "http.response.body", "body": encoded, "more_body": False})
                return
            await send(message)

        await self.app(scope, receive, capture)


def install_whatsapp_property_import_ui(app) -> None:
    app.add_middleware(WhatsAppPropertyImportUIMiddleware)
