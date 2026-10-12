# Local Mock Telephony

The mock endpoint is disabled by default. To test locally, set:

```bash
export METROCRM_ENABLE_MOCK_TELEPHONY=1
uvicorn app.main_portal:app --reload
```

PowerShell:

```powershell
$env:METROCRM_ENABLE_MOCK_TELEPHONY = "1"
uvicorn app.main_portal:app --reload
```

Endpoint: `POST /api/telephony/mock-call`

```json
{
  "executive_id": "exec-1",
  "client_phone": "+91 98765 43210",
  "lead_name": "Example Lead"
}
```

This only creates a simulated response and a `MOCK-...` call SID. It never calls a telephone number. Keep `METROCRM_ENABLE_MOCK_TELEPHONY` unset on Render/production.

A standalone React example is at `frontend-examples/MockCallButton.tsx`. The existing MetroCRM production UI is FastAPI/Jinja and is not changed to React by this addition.
