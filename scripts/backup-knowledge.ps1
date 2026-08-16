[CmdletBinding()]
param(
    [string]$Message = "knowledge: $(Get-Date -Format 'yyyy-MM-dd HH:mm')",
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$repo = Join-Path $root 'vault'
$safeRepo = [System.IO.Path]::GetFullPath($repo).Replace('\', '/')

function Invoke-KnowledgeGit {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $output = & git -c "safe.directory=$safeRepo" -C $repo @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Knowledge git $($Arguments -join ' ') failed:`n$($output -join [Environment]::NewLine)"
    }
    return @($output)
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git is not available in PATH.' }
if (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) {
    throw "The knowledge-data repository is not initialized: $repo"
}

$statusBefore = @(Invoke-KnowledgeGit status --short)
if ($statusBefore.Count -eq 0) {
    Write-Host 'Knowledge data is already up to date.' -ForegroundColor Green
    exit 0
}
if ($DryRun) {
    Write-Host 'Dry run: knowledge-data changes:' -ForegroundColor Cyan
    $statusBefore | ForEach-Object { Write-Host $_ }
    Write-Host 'No files were staged, committed, or pushed.' -ForegroundColor Yellow
    exit 0
}

$remoteNames = @(Invoke-KnowledgeGit remote)
if ($remoteNames -notcontains 'origin') {
    throw 'Knowledge-data remote origin is not configured. See RESTORE.md.'
}
$null = Invoke-KnowledgeGit fetch origin
$upstream = (& git -c "safe.directory=$safeRepo" -C $repo rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>$null)
if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($upstream)) {
    & git -c "safe.directory=$safeRepo" -C $repo merge-base --is-ancestor $upstream HEAD
    if ($LASTEXITCODE -ne 0) { throw "Remote knowledge changes exist on $upstream. Integrate them before backup." }
}

$null = Invoke-KnowledgeGit add -- .
& git -c "safe.directory=$safeRepo" -C $repo diff --cached --quiet
if ($LASTEXITCODE -eq 0) { Write-Host 'Only ignored files changed; there is nothing to back up.' -ForegroundColor Green; exit 0 }
if ($LASTEXITCODE -ne 1) { throw 'Unable to inspect staged knowledge changes.' }

$null = Invoke-KnowledgeGit commit -m $Message
$null = Invoke-KnowledgeGit push
Write-Host 'Knowledge-data backup committed and pushed successfully.' -ForegroundColor Green
