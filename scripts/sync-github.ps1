[CmdletBinding()]
param(
    [string]$ConfigPath = ''
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    $ConfigPath = Join-Path $PSScriptRoot 'project-config.psd1'
}

function Write-Step {
    param([string]$Scope, [string]$Message, [ConsoleColor]$Color = [ConsoleColor]::Gray)
    Write-Host ("[{0}] [{1}] {2}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Scope, $Message) -ForegroundColor $Color
}

function Invoke-Git {
    param([string]$RepositoryPath, [string[]]$Arguments)
    $safePath = [System.IO.Path]::GetFullPath($RepositoryPath).Replace('\', '/')
    $output = & git -c "safe.directory=$safePath" -C $RepositoryPath @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed: $($output -join [Environment]::NewLine)"
    }
    return @($output)
}

function Read-BranchState {
    param([string]$Path)
    $state = @{}
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $state }
    $raw = (Get-Content -LiteralPath $Path -Raw -Encoding UTF8).Trim()
    if ([string]::IsNullOrWhiteSpace($raw)) { return $state }
    $parsed = $raw | ConvertFrom-Json
    foreach ($property in @($parsed.PSObject.Properties)) {
        if ($property.Value -is [string] -and -not [string]::IsNullOrWhiteSpace([string]$property.Value)) {
            $state[$property.Name] = [string]$property.Value
        }
    }
    return $state
}

function Write-BranchStateAtomically {
    param([string]$Path, [hashtable]$State)
    $ordered = [ordered]@{}
    foreach ($key in @($State.Keys | Sort-Object)) { $ordered[$key] = $State[$key] }
    $json = $ordered | ConvertTo-Json -Depth 3
    $tempPath = "$Path.tmp"
    [System.IO.File]::WriteAllText($tempPath, "$json`r`n", [System.Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $tempPath -Destination $Path -Force
}

function ConvertFrom-Utf8Base64 {
    param([string]$Value)
    try { return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($Value)) }
    catch { throw 'Invalid ProjectPageUtf8Base64 value in project config.' }
}

function Get-DefaultRemoteBranch {
    param([string]$RepositoryPath)
    $ref = (Invoke-Git $RepositoryPath @('symbolic-ref', '--quiet', 'refs/remotes/origin/HEAD') | Select-Object -First 1).Trim()
    if ([string]::IsNullOrWhiteSpace($ref) -or -not $ref.StartsWith('refs/remotes/')) {
        throw 'Cannot determine the default remote branch from origin/HEAD.'
    }
    return $ref.Substring('refs/remotes/'.Length)
}

function Get-RemoteBranches {
    param([string]$RepositoryPath)
    $lines = Invoke-Git $RepositoryPath @(
        'for-each-ref', '--sort=-committerdate',
        '--format=%(refname:short)|%(objectname)|%(committerdate:iso-strict)',
        'refs/remotes/origin/'
    )
    $branches = @()
    foreach ($line in $lines) {
        $parts = ([string]$line).Split('|', 3)
        if ($parts.Count -ne 3) { continue }
        $branchName = $parts[0]
        if ($branchName -eq 'origin' -or $branchName -eq 'origin/HEAD') { continue }
        $branches += [pscustomobject]@{
            Name = $branchName
            Sha = $parts[1]
            CommitTime = [datetimeoffset]::Parse($parts[2])
        }
    }
    return @($branches)
}

if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "Project config not found: $ConfigPath"
}

$config = Import-PowerShellDataFile -LiteralPath $ConfigPath
$root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$reposRoot = Join-Path $root 'repos'
$stateRoot = Join-Path $root 'vault\system\sync-state\github'
$projectPagesRoot = Join-Path $root 'vault\wiki\projects'

foreach ($requiredPath in @($reposRoot, $stateRoot, $projectPagesRoot)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Container)) {
        throw "Required directory not found: $requiredPath"
    }
}

$failures = New-Object System.Collections.Generic.List[string]
$ghChecked = $false
$ghAuthenticated = $false

foreach ($project in @($config.Projects)) {
    $name = [string]$project.Name
    $scope = $name
    try {
        foreach ($field in @('Name', 'Directory', 'Repository', 'ProjectPageUtf8Base64', 'StateFile')) {
            if ([string]::IsNullOrWhiteSpace([string]$project[$field])) { throw "Missing project config field: $field" }
        }

        $repoPath = [System.IO.Path]::GetFullPath((Join-Path $reposRoot ([string]$project.Directory)))
        if (-not $repoPath.StartsWith($reposRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Repository path escapes repos root: $repoPath"
        }

        if (-not (Test-Path -LiteralPath (Join-Path $repoPath '.git') -PathType Container)) {
            if (-not $ghChecked) {
                & gh auth status 2>&1 | ForEach-Object { Write-Step 'GitHub Auth' ([string]$_) DarkGray }
                $ghAuthenticated = ($LASTEXITCODE -eq 0)
                $ghChecked = $true
            }
            if (-not $ghAuthenticated) {
                throw 'GitHub CLI is not authenticated. Run gh auth login; clone was not attempted.'
            }
            if ((Test-Path -LiteralPath $repoPath) -and @(Get-ChildItem -LiteralPath $repoPath -Force).Count -gt 0) {
                throw "Clone target exists and is not empty: $repoPath"
            }
            Write-Step $scope "Cloning $($project.Repository) with gh repo clone." Cyan
            & gh repo clone ([string]$project.Repository) $repoPath
            if ($LASTEXITCODE -ne 0) { throw "gh repo clone failed with exit code $LASTEXITCODE" }
        }

        Write-Step $scope 'Checking remote and worktree status.' Cyan
        $null = Invoke-Git $repoPath @('remote', '-v')
        $null = Invoke-Git $repoPath @('status', '--short', '--branch')
        Write-Step $scope 'Fetching all remotes and pruning stale refs.' Cyan
        $null = Invoke-Git $repoPath @('fetch', '--all', '--prune')

        $defaultBranch = Get-DefaultRemoteBranch $repoPath
        $branchInfos = @(Get-RemoteBranches $repoPath)
        if ($branchInfos.Count -eq 0) { throw 'No origin remote branches found.' }
        $activeBranch = $branchInfos | Sort-Object CommitTime -Descending | Select-Object -First 1
        Write-Step $scope "Default=$defaultBranch; active=$($activeBranch.Name); remote branches=$($branchInfos.Count)." Green

        $statePath = Join-Path $stateRoot ([string]$project.StateFile)
        $state = Read-BranchState $statePath
        $orderedBranches = @($branchInfos | Sort-Object @{ Expression = { if ($_.Name -eq $defaultBranch) { 0 } else { 1 } } }, Name)

        foreach ($branch in $orderedBranches) {
            $branchScope = "$name/$($branch.Name)"
            try {
                $newSha = [string]$branch.Sha
                $oldSha = if ($state.ContainsKey($branch.Name)) { [string]$state[$branch.Name] } else { '' }
                if ($oldSha -eq $newSha) {
                    Write-Step $branchScope "Unchanged at $newSha; skipped." DarkGray
                    continue
                }

                $operation = 'GITHUB_UPDATE'
                $baseSha = ''
                $range = ''
                $analysisRule = ''
                if ([string]::IsNullOrWhiteSpace($oldSha)) {
                    if ($branch.Name -eq $defaultBranch) {
                        $operation = 'GITHUB_INGEST'
                        $range = "baseline at $newSha"
                        $analysisRule = 'This is the first default-branch baseline. Understand the project core and create or update its one long-lived Project page.'
                    }
                    else {
                        $baseSha = (Invoke-Git $repoPath @('merge-base', $defaultBranch, $branch.Name) | Select-Object -First 1).Trim()
                        if ([string]::IsNullOrWhiteSpace($baseSha)) { throw 'No merge-base found for the new branch.' }
                        $range = "$baseSha..$newSha"
                        $analysisRule = "This is a newly discovered branch. Analyze only git log and git diff for $range; never analyze its full history."
                    }
                }
                else {
                    $null = Invoke-Git $repoPath @('rev-parse', '--verify', "$oldSha^{commit}")
                    $range = "$oldSha..$newSha"
                    $analysisRule = "This is an existing branch update. Analyze only git log and git diff for $range."
                }

                $projectPageName = ConvertFrom-Utf8Base64 ([string]$project.ProjectPageUtf8Base64)
                $projectPage = Join-Path $projectPagesRoot $projectPageName
                $agentsPath = Join-Path $root 'AGENTS.md'
                $prompt = @"
Follow $agentsPath and execute $operation for exactly one remote branch.
Project: $name
Repository: $repoPath
Project page: $projectPage
Default remote branch: $defaultBranch
Remote branch: $($branch.Name)
Latest branch commit time: $($branch.CommitTime.ToString('o'))
OLD_SHA: $oldSha
BASE_SHA: $baseSha
NEW_SHA: $newSha
Analysis range: $range

$analysisRule
When running Git under a sandbox, use: git -c safe.directory=$($repoPath.Replace('\', '/')) -C $repoPath ...
Treat repos as a read-only fact source. Never edit, delete, format, checkout, merge, add, commit, push, reset, clean, or change repository configuration. Only vault, scripts, AGENTS.md, and README.md are writable; vault/raw and vault/journal/daily/raw are read-only.
Update Project, Wiki, Insights, Index, and Log only when facts warrant it. Clearly distinguish merged, developed but unmerged, in development, testing, verified, and unconfirmed. A feature branch is not automatically completed. Do not write any sync-state JSON; the caller updates this branch key only after your successful exit.
"@

                Write-Step $branchScope "Running Codex for $range" Yellow
                Push-Location $root
                try {
                    & codex exec --sandbox workspace-write $prompt
                    $codexExit = $LASTEXITCODE
                }
                finally { Pop-Location }
                if ($codexExit -ne 0) { throw "codex exec failed with exit code $codexExit" }

                $state[$branch.Name] = $newSha
                Write-BranchStateAtomically $statePath $state
                Write-Step $branchScope "Knowledge updated; state advanced to $newSha." Green
            }
            catch {
                $message = $_.Exception.Message
                $failures.Add("${branchScope}: $message")
                Write-Step $branchScope "FAILED: $message; state not advanced." Red
            }
        }
    }
    catch {
        $message = $_.Exception.Message
        $failures.Add("${scope}: $message")
        Write-Step $scope "FAILED: $message" Red
    }
}

if ($failures.Count -gt 0) {
    Write-Host "Sync completed with $($failures.Count) failure(s):" -ForegroundColor Yellow
    $failures | ForEach-Object { Write-Host "- $_" -ForegroundColor Yellow }
    exit 1
}

Write-Host 'All repositories and remote branches synchronized successfully.' -ForegroundColor Green
exit 0
