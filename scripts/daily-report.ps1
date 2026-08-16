[CmdletBinding()]
param(
    [datetime]$Date = (Get-Date)
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$dateText = $Date.ToString('yyyy-MM-dd')
$rawPath = Join-Path $root "vault\journal\daily\raw\$dateText.md"
$organizedPath = Join-Path $root "vault\journal\daily\organized\$dateText.md"
$templatePath = Join-Path $root 'vault\system\templates\daily.md'
$agentsPath = Join-Path $root 'AGENTS.md'

if (-not (Test-Path -LiteralPath $rawPath -PathType Leaf)) {
    throw "Raw daily report not found: $rawPath. Create this Markdown file manually before organizing the report."
}

$rawHashBefore = (Get-FileHash -LiteralPath $rawPath -Algorithm SHA256).Hash
if (-not (Test-Path -LiteralPath $organizedPath -PathType Leaf)) {
    $template = Get-Content -LiteralPath $templatePath -Raw -Encoding UTF8
    $initial = $template.Replace('{{DATE}}', $dateText)
    [System.IO.File]::WriteAllText($organizedPath, $initial, [System.Text.UTF8Encoding]::new($false))
}

$prompt = @"
Follow $agentsPath. Prepare the daily report for $dateText by executing DAILY_REPORT, then execute DISTILL.
Immutable raw fact source: $rawPath
Organized output: $organizedPath
Never edit, delete, rename, move, format, or overwrite the raw daily file. Use it as the primary human record. GitHub activity across every relevant remote branch may supplement and verify the human record, but must not replace it.
Use verified commits and diffs from all four repositories, Project pages, Insights, Wiki changes, and system/log.md. Do not invent facts and do not treat feature-branch work as merged or completed without evidence.
Treat repos, vault/raw, and vault/journal/daily/raw as read-only. Only organized knowledge outputs, scripts, AGENTS.md, and README.md are writable.
"@

Push-Location $root
try {
    & codex exec --sandbox workspace-write $prompt
    $codexExit = $LASTEXITCODE
}
finally { Pop-Location }

$rawHashAfter = (Get-FileHash -LiteralPath $rawPath -Algorithm SHA256).Hash
if ($rawHashAfter -cne $rawHashBefore) {
    throw 'SAFETY VIOLATION: the immutable raw daily report changed during Codex execution. The script did not accept the result.'
}
if ($codexExit -ne 0) { throw "codex exec failed with exit code $codexExit" }
Write-Host "Daily report and distillation completed: $organizedPath" -ForegroundColor Green
