[CmdletBinding()]
param(
    [switch]$InstallMediaTools,
    [switch]$WithOcr,
    [switch]$WithLux
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $PSScriptRoot '.venv-video-knowledge'
$python = Join-Path $venv 'Scripts\python.exe'
$requirements = Join-Path $PSScriptRoot 'requirements-video-knowledge.txt'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    python -m venv $venv
}

& $python -m pip install --upgrade pip
& $python -m pip install -r $requirements
if ($WithOcr) {
    & $python -m pip install -r (Join-Path $PSScriptRoot 'requirements-video-knowledge-ocr.txt')
}

if ($WithLux) {
    $luxVersion = '0.24.1'
    $luxDirectory = Join-Path $PSScriptRoot 'tools\lux'
    $luxArchive = Join-Path $luxDirectory "lux_$($luxVersion)_Windows_x86_64.zip"
    $luxChecksum = Join-Path $luxDirectory "lux_$($luxVersion)_checksums.txt"
    New-Item -ItemType Directory -Path $luxDirectory -Force | Out-Null
    Invoke-WebRequest -Uri "https://github.com/iawia002/lux/releases/download/v$luxVersion/lux_$($luxVersion)_Windows_x86_64.zip" -OutFile $luxArchive
    Invoke-WebRequest -Uri "https://github.com/iawia002/lux/releases/download/v$luxVersion/lux_$($luxVersion)_checksums.txt" -OutFile $luxChecksum
    $expectedLine = Get-Content -LiteralPath $luxChecksum | Where-Object { $_ -match "lux_$([regex]::Escape($luxVersion))_Windows_x86_64.zip$" } | Select-Object -First 1
    if (-not $expectedLine) { throw 'Lux checksum entry was not found.' }
    $expectedHash = ($expectedLine -split '\s+')[0].ToUpperInvariant()
    $actualHash = (Get-FileHash -LiteralPath $luxArchive -Algorithm SHA256).Hash
    if ($actualHash -cne $expectedHash) { throw 'Lux archive checksum verification failed.' }
    Expand-Archive -LiteralPath $luxArchive -DestinationPath $luxDirectory -Force
}

if ($InstallMediaTools) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'winget is unavailable. Install FFmpeg and yt-dlp manually, then run video-knowledge.ps1 doctor.'
    }
    winget install --id Gyan.FFmpeg --exact --accept-package-agreements --accept-source-agreements
    winget install --id yt-dlp.yt-dlp --exact --accept-package-agreements --accept-source-agreements
}

Write-Host 'Local video knowledge environment is ready. Model weights download on first transcription.' -ForegroundColor Green
if (-not $WithOcr) {
    Write-Host 'RapidOCR was not installed; rerun with -WithOcr only when local OCR is needed.'
}
if (-not $WithLux) {
    Write-Host 'Lux fallback was not installed; rerun with -WithLux when Douyin/Bilibili needs the second downloader.'
}
Write-Host "Run: powershell -File .\scripts\video-knowledge.ps1 doctor"
