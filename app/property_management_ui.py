from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class PropertyManagementUIMiddleware:
    """Add small UI controls without changing existing large templates.

    The backend routes remain the security boundary. This middleware only adds
    the per-project delete form and the Activity Log navigation item to the
    already-rendered authenticated HTML pages.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path not in {"/dashboard", "/admin/property-data", "/super-admin/property-data", "/admin/users", "/super-admin/users"}:
            await self.app(scope, receive, send)
            return

        started: Message | None = None
        body_parts: list[bytes] = []

        async def capture(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = message
                return
            if message["type"] == "http.response.body":
                body_parts.append(message.get("body", b""))
                if message.get("more_body", False):
                    return
                if started is None:
                    await send(message)
                    return
                body = b"".join(body_parts)
                headers = list(started.get("headers", []))
                content_type = b""
                for key, value in headers:
                    if key.lower() == b"content-type":
                        content_type = value.lower()
                        break
                if b"text/html" not in content_type:
                    await send(started)
                    await send(message)
                    return
                html = body.decode("utf-8", errors="replace")
                html = self._inject(html, path)
                encoded = html.encode("utf-8")
                headers = [(k, v) for k, v in headers if k.lower() != b"content-length"]
                headers.append((b"content-length", str(len(encoded)).encode("ascii")))
                new_start = dict(started)
                new_start["headers"] = headers
                await send(new_start)
                await send({"type": "http.response.body", "body": encoded, "more_body": False})
                return
            await send(message)

        await self.app(scope, receive, capture)

    @staticmethod
    def _inject(html: str, path: str) -> str:
        if "metrocrm-property-management-ui" in html:
            return html
        script = """
<script id="metrocrm-property-management-ui">
(function(){
  const roleEl=document.querySelector('.profile-role');
  const role=roleEl ? roleEl.textContent.trim().toUpperCase() : '';
  const workspaceNav=document.querySelector('.sidebar .nav');
  if(workspaceNav && (role==='SUPER_ADMIN' || role==='ADMIN') && !document.getElementById('metrocrm-activity-nav')){
    const link=document.createElement('a');
    link.id='metrocrm-activity-nav';
    link.href=role==='SUPER_ADMIN'?'/super-admin/activity-log':'/admin/activity-log';
    link.innerHTML='<span class="icon">◉</span>'+(role==='SUPER_ADMIN'?'User Activity & Audit':'User Activity (Approval)');
    if(location.pathname.includes('/activity-log')) link.classList.add('active');
    workspaceNav.appendChild(link);
  }
  if((location.pathname==='/admin/property-data' || location.pathname==='/super-admin/property-data') && new URLSearchParams(location.search).get('entity')!=='Projects') return;
  if(location.pathname==='/admin/property-data' || location.pathname==='/super-admin/property-data'){
    const table=document.querySelector('.pd-table tbody');
    const csrf=document.querySelector('input[name="csrf_token"]');
    if(!table || !csrf) return;
    const base=location.pathname.startsWith('/super-admin/')?'/super-admin/property-data':'/admin/property-data';
    table.querySelectorAll('tr').forEach(function(row){
      const cells=row.querySelectorAll('td');
      if(cells.length<3) return;
      const id=(cells[0].textContent||'').trim();
      if(!/^\\d+$/.test(id) || row.querySelector('.metrocrm-delete-property')) return;
      const form=document.createElement('form');
      form.method='post'; form.action=base+'/projects/'+id+'/delete'; form.className='metrocrm-delete-property';
      form.style.display='inline';
      const token=document.createElement('input'); token.type='hidden'; token.name='csrf_token'; token.value=csrf.value;
      const button=document.createElement('button'); button.type='submit'; button.className='pd-btn danger'; button.textContent='🗑 Delete';
      button.title='Delete this property';
      button.addEventListener('click',function(event){
        const name=(cells[1].textContent||'').trim().replace(/\\s+/g,' ');
        if(!window.confirm('Delete this property and its linked property-only records? This cannot be undone.'+(name?'\\n\\n'+name:''))) event.preventDefault();
      });
      form.appendChild(token); form.appendChild(button); cells[2].appendChild(document.createTextNode(' ')); cells[2].appendChild(form);
    });
  }
})();
</script>
"""
        marker = "</body>"
        return html.replace(marker, script + marker, 1) if marker in html else html + script


def install_property_management_ui(app) -> None:
    app.add_middleware(PropertyManagementUIMiddleware)
