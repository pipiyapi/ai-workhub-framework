[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$EmptyKnowledge,
    [switch]$SkipProjectClone,
    [string]$KnowledgeRepository = 'pipiyapi/ai-workhub-knowledge-data'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$configPath = Join-Path $PSScriptRoot 'project-config.psd1'
$vault = Join-Path $root 'vault'
$reposRoot = Join-Path $root 'repos'
$referenceReposRoot = Join-Path $root 'references\repos'

function Write-Step { param([string]$Message, [ConsoleColor]$Color = [ConsoleColor]::Gray); Write-Host ("[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $Message) -ForegroundColor $Color }
function Test-CommandAvailable {
    param([string]$Name, [switch]$Required)
    $available = $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
    if ($available) { Write-Step "$Name is available." Green }
    elseif ($Required) { throw "$Name is required but was not found in PATH." }
    else { Write-Step "$Name was not found in PATH." Yellow }
    return $available
}
function Assert-CloneTarget {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    if (Test-Path -LiteralPath (Join-Path $Path '.git')) { return }
    if (@(Get-ChildItem -LiteralPath $Path -Force -ErrorAction Stop).Count -gt 0) { throw "Clone target is non-empty and is not a Git repository: $Path" }
}

Write-Step "AI WorkHub framework root: $root" Cyan
$null = Test-CommandAvailable git -Required
$ghAvailable = Test-CommandAvailable gh
$codexAvailable = Test-CommandAvailable codex
if (-not (Test-Path -LiteralPath (Join-Path $root 'AGENTS.md') -PathType Leaf)) { throw 'AGENTS.md is missing.' }
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { throw "Project configuration is missing: $configPath" }

if (-not (Test-Path -LiteralPath $vault)) {
    if ($EmptyKnowledge) {
        if ($CheckOnly) { Write-Step "Would create an empty knowledge repository: $vault" Yellow }
        else {
            $null = New-Item -ItemType Directory -Path $vault -Force
            & git -C $vault init -b main
            if ($LASTEXITCODE -ne 0) { throw 'Failed to initialize the empty knowledge repository.' }
            Write-Step "Created empty knowledge repository: $vault" Green
        }
    }
    else {
        if (-not $ghAvailable) { throw 'GitHub CLI is required to restore the private knowledge-data repository.' }
        if ($CheckOnly) { Write-Step "Would clone $KnowledgeRepository into $vault" Yellow }
        else {
            & gh auth status
            if ($LASTEXITCODE -ne 0) { throw 'GitHub CLI authentication failed in the normal Windows account.' }
            & gh repo clone $KnowledgeRepository $vault
            if ($LASTEXITCODE -ne 0) { throw 'Failed to clone the knowledge-data repository.' }
            Write-Step "Restored knowledge data: $vault" Green
        }
    }
}
elseif (-not (Test-Path -LiteralPath (Join-Path $vault '.git'))) {
    throw "The vault exists but is not an independent Git repository: $vault"
}
else { Write-Step 'Knowledge-data repository is present.' Green }

& (Join-Path $PSScriptRoot 'install-vault-template.ps1') -Destination $vault -CheckOnly:$CheckOnly
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

foreach ($path in @($reposRoot, $referenceReposRoot)) {
    if (-not (Test-Path -LiteralPath $path)) {
        if ($CheckOnly) { Write-Step "Would create: $path" Yellow }
        else { $null = New-Item -ItemType Directory -Path $path -Force; Write-Step "Created: $path" Green }
    }
}

if ($SkipProjectClone) { Write-Step 'Internal project cloning was skipped.' Yellow }
else {
    if (-not $ghAvailable) { throw 'GitHub CLI is required to restore internal repositories.' }
    if (-not $CheckOnly) { & gh auth status; if ($LASTEXITCODE -ne 0) { throw 'GitHub CLI authentication failed.' } }
    $config = Import-PowerShellDataFile -LiteralPath $configPath
    foreach ($project in @($config.Projects)) {
        $target = Join-Path $reposRoot ([string]$project.Directory)
        Assert-CloneTarget $target
        if (Test-Path -LiteralPath (Join-Path $target '.git')) { Write-Step "Already restored: $($project.Name)" DarkGray }
        elseif ($CheckOnly) { Write-Step "Would clone: $($project.Repository) -> $target" Yellow }
        else { & gh repo clone ([string]$project.Repository) $target; if ($LASTEXITCODE -ne 0) { throw "Failed to clone $($project.Name)." } }
    }
    $aiSchoolPath = Join-Path $reposRoot 'AI-School'
    Assert-CloneTarget $aiSchoolPath
    if (Test-Path -LiteralPath (Join-Path $aiSchoolPath '.git')) { Write-Step 'Already restored: AI-School' DarkGray }
    elseif ($CheckOnly) { Write-Step "Would clone AI-School -> $aiSchoolPath" Yellow }
    else { & git clone 'https://gitee.com/pipiyapi/AI-School' $aiSchoolPath; if ($LASTEXITCODE -ne 0) { throw 'Failed to clone AI-School.' } }
}

Write-Step 'Framework and knowledge-data composition is ready.' Green
if (-not $codexAvailable) { Write-Step 'Install Codex before running knowledge workflows.' Yellow }
Write-Step "Open in Codex: $root" Cyan
Write-Step "Open in Obsidian: $vault" Cyan
