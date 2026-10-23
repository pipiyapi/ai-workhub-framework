[CmdletBinding()]
param(
    [string]$Destination,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$templateRoot = Join-Path $PSScriptRoot 'vault-template'
if ([string]::IsNullOrWhiteSpace($Destination)) {
    $Destination = Join-Path $root 'vault'
}
$Destination = [System.IO.Path]::GetFullPath($Destination)

if (-not (Test-Path -LiteralPath $templateRoot -PathType Container)) {
    throw "Vault template is missing: $templateRoot"
}

$directories = @(
    'skills',
    'journal\daily\raw',
    'journal\daily\organized',
    'journal\weekly',
    'raw\web',
    'raw\github',
    'raw\papers',
    'raw\notes',
    'raw\video',
    'outputs\video-knowledge\notes',
    'outputs\video-knowledge\assets',
    'outputs\video-knowledge\media',
    'system\sync-state\github',
    'wiki\concepts',
    'wiki\technologies',
    'wiki\insights',
    'wiki\projects',
    'wiki\references'
)

foreach ($relative in $directories) {
    $target = Join-Path $Destination $relative
    if (-not (Test-Path -LiteralPath $target)) {
        if ($CheckOnly) { Write-Host "Would create directory: $target" -ForegroundColor Yellow }
        else { $null = New-Item -ItemType Directory -Path $target -Force; Write-Host "Created directory: $target" -ForegroundColor Green }
    }
}

foreach ($source in Get-ChildItem -LiteralPath $templateRoot -Recurse -File) {
    $relative = $source.FullName.Substring($templateRoot.Length).TrimStart('\')
    $target = Join-Path $Destination $relative
    if (Test-Path -LiteralPath $target) {
        Write-Host "Kept existing file: $target" -ForegroundColor DarkGray
        continue
    }
    if ($CheckOnly) {
        Write-Host "Would install template file: $target" -ForegroundColor Yellow
        continue
    }
    $parent = Split-Path -Parent $target
    $null = New-Item -ItemType Directory -Path $parent -Force
    Copy-Item -LiteralPath $source.FullName -Destination $target
    Write-Host "Installed template file: $target" -ForegroundColor Green
}
