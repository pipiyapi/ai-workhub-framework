[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9]+(?:-[a-z0-9]+)*$')]
    [string]$Name,
    [string]$VaultPath,
    [string]$Destination,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($VaultPath)) { $VaultPath = Join-Path $root 'vault' }
if ([string]::IsNullOrWhiteSpace($Destination)) {
    $codexPath = $env:CODEX_HOME
    if ([string]::IsNullOrWhiteSpace($codexPath)) { $codexPath = Join-Path $env:USERPROFILE '.codex' }
    $Destination = Join-Path $codexPath 'skills'
}
$collection = [IO.Path]::GetFullPath((Join-Path $VaultPath 'skills'))
$source = [IO.Path]::GetFullPath((Join-Path $collection $Name))
$destinationRoot = [IO.Path]::GetFullPath($Destination)
$target = [IO.Path]::GetFullPath((Join-Path $destinationRoot $Name))
if (-not (Test-Path -LiteralPath $source -PathType Container)) { throw "Collected skill not found: $Name" }
if (-not (Test-Path -LiteralPath (Join-Path $source 'SKILL.md') -PathType Leaf)) { throw "SKILL.md is missing: $Name" }
if (Test-Path -LiteralPath $target) { throw "Destination already exists; compare versions before replacing: $target" }
# Reject linked roots/ancestors and nested links before copying any content.
foreach ($pathToCheck in @($source, $destinationRoot)) {
    $ancestor = $pathToCheck
    while ($ancestor) {
        if (Test-Path -LiteralPath $ancestor) {
            $item = Get-Item -LiteralPath $ancestor -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked paths are not supported: $ancestor" }
        }
        $parent = Split-Path -Parent $ancestor
        if ($parent -eq $ancestor) { break }
        $ancestor = $parent
    }
}
$sourcePrefix = $source.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
if ($destinationRoot.Equals($source, [StringComparison]::OrdinalIgnoreCase) -or $destinationRoot.StartsWith($sourcePrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Destination must not be inside the source skill.'
}
$items = @(Get-ChildItem -LiteralPath $source -Recurse -Force)
foreach ($item in $items) {
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked content is not supported: $($item.FullName)" }
    if ($item.Name -eq '.git' -or $item.Name -eq '.env' -or $item.Name.StartsWith('.env.')) { throw "Runtime or secret content must not be installed: $($item.Name)" }
}
$entry = Get-Content -LiteralPath (Join-Path $source 'SKILL.md') -Raw -Encoding UTF8
if ($entry -notmatch ('(?m)^name:\s*' + [regex]::Escape($Name) + '\s*$')) { throw 'Folder name and SKILL.md name do not match.' }
if ($CheckOnly) { Write-Output "Ready to install $Name to $target"; return }
$null = New-Item -ItemType Directory -Path $destinationRoot -Force
# Stage beside the destination, then rename; never overwrite an existing skill.
$staging = Join-Path $destinationRoot ('.install-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $staging
try {
    Get-ChildItem -LiteralPath $source -Force | Copy-Item -Destination $staging -Recurse
    Move-Item -LiteralPath $staging -Destination $target
} catch {
    # Keep the private staging directory for inspection on failure.
    throw "Installation failed; staged files may remain at $staging. $($_.Exception.Message)"
}
Write-Output "Installed $Name to $target. Available on the next Codex turn."
