[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$syncScript = Join-Path $PSScriptRoot 'sync-github.ps1'

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $syncScript
exit $LASTEXITCODE
