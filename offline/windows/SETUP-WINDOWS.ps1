$ErrorActionPreference = "Stop"

Write-Host "=== MetroCRM Offline Windows Setup ===" -ForegroundColor Cyan

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python is not installed or is not on PATH. Install Python 3.11+ and rerun this script."
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is not installed or is not on PATH. Install Git for Windows and rerun this script."
}

$pythonVersion = python --version
$gitVersion = git --version
Write-Host $pythonVersion
Write-Host $gitVersion

if (-not (Test-Path ".venv")) {
    Write-Host "Creating Python virtual environment..."
    python -m venv .venv
}

Write-Host "Activating virtual environment..."
& ".\.venv\Scripts\Activate.ps1"

Write-Host "Upgrading pip..."
python -m pip install --upgrade pip

Write-Host "Installing MetroCRM dependencies..."
python -m pip install -r requirements.txt

if (-not (Test-Path ".env")) {
    Write-Host "Creating local .env from .env.example..."
    Copy-Item ".env.example" ".env"
}

# Force safe local defaults. Do not overwrite any real secret values.
$envPath = ".env"
$content = Get-Content $envPath -Raw
$content = [regex]::Replace($content, '(?m)^ENVIRONMENT=.*$', 'ENVIRONMENT=development')
$content = [regex]::Replace($content, '(?m)^DATABASE_URL=.*$', 'DATABASE_URL=sqlite:///./metrocrm.db')
$content = [regex]::Replace($content, '(?m)^BACKUP_CLOUD_PROVIDER=.*$', 'BACKUP_CLOUD_PROVIDER=none')
$content = [regex]::Replace($content, '(?m)^BACKUP_CLOUD_PROVIDERS=.*$', 'BACKUP_CLOUD_PROVIDERS=')
$content = [regex]::Replace($content, '(?m)^LEAD_INTEGRATIONS_ENABLED=.*$', 'LEAD_INTEGRATIONS_ENABLED=false')
$content = [regex]::Replace($content, '(?m)^WHATSAPP_ENABLED=.*$', 'WHATSAPP_ENABLED=false')
$content = [regex]::Replace($content, '(?m)^EMAIL_PROVIDER=.*$', 'EMAIL_PROVIDER=test')
Set-Content -Path $envPath -Value $content -Encoding UTF8

New-Item -ItemType Directory -Force -Path ".\backups" | Out-Null
New-Item -ItemType Directory -Force -Path ".\uploads" | Out-Null

Write-Host ""
Write-Host "MetroCRM offline environment is prepared." -ForegroundColor Green
Write-Host "Start with: offline\windows\RUN-METROCRM.bat"
Write-Host "Local URL: http://127.0.0.1:8000"
