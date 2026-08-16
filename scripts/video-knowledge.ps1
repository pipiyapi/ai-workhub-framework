[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Position = 0)]
    [ValidateSet('doctor', 'audit', 'inspect', 'ingest', 'batch-ingest')]
    [string]$Command = 'doctor',

    [Parameter(Position = 1)]
    [string]$InputText,

    [string]$BatchFile,

    [ValidateSet('talk', 'visual')]
    [string]$Mode,

    [ValidateSet('funasr-paraformer', 'funasr-sensevoice', 'none')]
    [string]$AsrBackend,

    [switch]$KeepVideo,
    [switch]$EnableOcr,
    [string]$CookiesFromBrowser
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $PSScriptRoot '.venv-video-knowledge\Scripts\python.exe'
$python = if (Test-Path -LiteralPath $venvPython -PathType Leaf) { $venvPython } else { 'python' }
$entry = Join-Path $PSScriptRoot 'video_knowledge.py'
$localToolPath = Join-Path $PSScriptRoot 'tools\lux'
if (Test-Path -LiteralPath $localToolPath -PathType Container) {
    $env:PATH = "$localToolPath;$env:PATH"
}

$arguments = @($entry, $Command, '--root', $root)
if ($InputText) { $arguments += @('--input', $InputText) }
if ($BatchFile) { $arguments += @('--batch-file', $BatchFile) }
if ($Mode) { $arguments += @('--mode', $Mode) }
if ($AsrBackend) { $arguments += @('--asr-backend', $AsrBackend) }
if ($KeepVideo) { $arguments += '--keep-video' }
if ($EnableOcr) { $arguments += '--enable-ocr' }
if ($CookiesFromBrowser) { $arguments += @('--cookies-from-browser', $CookiesFromBrowser) }

& $python @arguments
exit $LASTEXITCODE
