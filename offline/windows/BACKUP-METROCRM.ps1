$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$destinationRoot = Join-Path $root "offline-backups"
$archive = Join-Path $destinationRoot "MetroCRM-local-$stamp.zip"

New-Item -ItemType Directory -Force -Path $destinationRoot | Out-Null

$temp = Join-Path $env:TEMP "MetroCRM-backup-$stamp"
New-Item -ItemType Directory -Force -Path $temp | Out-Null

try {
    foreach ($name in @("metrocrm.db","uploads","backups")) {
        $source = Join-Path $root $name
        if (Test-Path $source) {
            Copy-Item $source (Join-Path $temp $name) -Recurse -Force
        }
    }

    Copy-Item (Join-Path $root ".env.example") (Join-Path $temp ".env.example") -Force

    Compress-Archive -Path (Join-Path $temp "*") -DestinationPath $archive -CompressionLevel Optimal

    Write-Host "Backup created:" -ForegroundColor Green
    Write-Host $archive
}
finally {
    if (Test-Path $temp) {
        Remove-Item $temp -Recurse -Force
    }
}
