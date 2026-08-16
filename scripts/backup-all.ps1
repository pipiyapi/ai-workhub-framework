[CmdletBinding()]
param([switch]$DryRun)

$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'backup-framework.ps1') -DryRun:$DryRun
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $PSScriptRoot 'backup-knowledge.ps1') -DryRun:$DryRun
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
