[CmdletBinding()]
param(
    [datetime]$Date = (Get-Date)
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$calendar = [System.Globalization.CultureInfo]::InvariantCulture.Calendar
$week = $calendar.GetWeekOfYear($Date, [System.Globalization.CalendarWeekRule]::FirstFourDayWeek, [DayOfWeek]::Monday)
$dayOffset = ([int]$Date.DayOfWeek + 6) % 7
$thursday = $Date.Date.AddDays(3 - $dayOffset)
$isoWeek = '{0}-W{1:D2}' -f $thursday.Year, $week
$weeklyPath = Join-Path $root "vault\journal\weekly\$isoWeek.md"
$templatePath = Join-Path $root 'vault\system\templates\weekly.md'
$agentsPath = Join-Path $root 'AGENTS.md'

if (-not (Test-Path -LiteralPath $weeklyPath -PathType Leaf)) {
    $template = Get-Content -LiteralPath $templatePath -Raw -Encoding UTF8
    $initial = $template.Replace('{{ISO_WEEK}}', $isoWeek)
    [System.IO.File]::WriteAllText($weeklyPath, $initial, [System.Text.UTF8Encoding]::new($false))
}

$prompt = @"
Follow $agentsPath and execute WEEKLY_REPORT.
Reference date: $($Date.ToString('yyyy-MM-dd')); ISO week: $isoWeek (Monday through Sunday).
Target file: $weeklyPath
Read organized daily reports under vault/journal/daily/organized first. Combine them with verified commits and remote-branch changes from all four repositories, Project pages, Insights, Wiki updates, and system/log.md. Read vault/journal/daily/raw only when a fact needs verification, and never modify raw files.
Generate both the complete internal report and the external three-column table. Merge daily activity into outcome-oriented statements. Do not exaggerate, invent completion, or treat feature-branch work as merged without evidence.
Treat repos, vault/raw, and vault/journal/daily/raw as read-only. Only organized knowledge outputs, scripts, AGENTS.md, and README.md are writable.
"@

Push-Location $root
try {
    & codex exec --sandbox workspace-write $prompt
    $codexExit = $LASTEXITCODE
}
finally { Pop-Location }

if ($codexExit -ne 0) { throw "codex exec failed with exit code $codexExit" }
Write-Host "Weekly reports completed: $weeklyPath" -ForegroundColor Green
