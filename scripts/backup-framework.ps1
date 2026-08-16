[CmdletBinding()]
param(
    [string]$Message = "framework: $(Get-Date -Format 'yyyy-MM-dd HH:mm')",
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$safeRepo = [System.IO.Path]::GetFullPath($repo).Replace('\', '/')

function Invoke-FrameworkGit {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $output = & git -c "safe.directory=$safeRepo" -C $repo @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Framework git $($Arguments -join ' ') failed:`n$($output -join [Environment]::NewLine)" }
    return @($output)
}

if (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) { throw "Framework repository is not initialized: $repo" }
$statusBefore = @(Invoke-FrameworkGit status --short)
if ($statusBefore.Count -eq 0) { Write-Host 'Framework is already up to date.' -ForegroundColor Green; exit 0 }
if ($DryRun) {
    Write-Host 'Dry run: framework changes:' -ForegroundColor Cyan
    $statusBefore | ForEach-Object { Write-Host $_ }
    Write-Host 'No files were staged, committed, or pushed.' -ForegroundColor Yellow
    exit 0
}

$remoteNames = @(Invoke-FrameworkGit remote)
if ($remoteNames -notcontains 'origin') { throw 'Framework remote origin is not configured. See RESTORE.md.' }
$null = Invoke-FrameworkGit fetch origin
$upstream = (& git -c "safe.directory=$safeRepo" -C $repo rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>$null)
if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($upstream)) {
    & git -c "safe.directory=$safeRepo" -C $repo merge-base --is-ancestor $upstream HEAD
    if ($LASTEXITCODE -ne 0) { throw "Remote framework changes exist on $upstream. Integrate them before backup." }
}

$null = Invoke-FrameworkGit add -- .gitignore AGENTS.md README.md RESTORE.md scripts
& git -c "safe.directory=$safeRepo" -C $repo diff --cached --quiet
if ($LASTEXITCODE -eq 0) { Write-Host 'Only excluded files changed; there is nothing to back up.' -ForegroundColor Green; exit 0 }
if ($LASTEXITCODE -ne 1) { throw 'Unable to inspect staged framework changes.' }
$null = Invoke-FrameworkGit commit -m $Message
$null = Invoke-FrameworkGit push
Write-Host 'Framework backup committed and pushed successfully.' -ForegroundColor Green
