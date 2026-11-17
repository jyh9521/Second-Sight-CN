param([Parameter(Mandatory=$true)][string]$Plan)
$ErrorActionPreference = 'Stop'
# Python may inherit PowerShell 7's module paths while invoking Windows PowerShell.
$env:PSModulePath = (Join-Path $PSHOME 'Modules') + [IO.Path]::PathSeparator + $env:PSModulePath
$project = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$allowed = [IO.Path]::GetFullPath((Join-Path $project 'dist'))
$record = Get-Content -LiteralPath $Plan -Raw | ConvertFrom-Json
if ($record.format -ne 'second-sight-retention-v1' -or $record.limit -ne 2 -or [IO.Path]::GetFullPath($record.root) -ne $allowed) { throw 'Unexpected retention plan/root' }
if (@($record.keep).Count -gt 2 -or @($record.keep).Count -lt 1) { throw 'Invalid keep set' }
if (@($record.remove).Count -gt 0 -and @($record.keep).Count -ne 2) { throw 'Deletion requires two retained packages' }
foreach ($entry in $record.keep) {
    $kept = [IO.Path]::GetFullPath([string]$entry.path)
    if ([IO.Path]::GetDirectoryName($kept) -ne $allowed -or [IO.Path]::GetFileName($kept) -ne $entry.name) { throw 'Invalid kept path' }
    if (-not (Test-Path -LiteralPath (Join-Path $kept 'package.json'))) { throw 'Kept package missing before pruning' }
}
function Assert-PlainTree([string]$path) {
    $item = Get-Item -LiteralPath $path -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse point rejected: $path" }
    if ($item.PSIsContainer) {
        foreach ($child in Get-ChildItem -LiteralPath $path -Force) { Assert-PlainTree $child.FullName }
    }
}
Assert-PlainTree $allowed
$targets = @()
foreach ($entry in $record.remove) {
    $target = [IO.Path]::GetFullPath([string]$entry.path)
    if ([IO.Path]::GetDirectoryName($target) -ne $allowed -or [IO.Path]::GetFileName($target) -ne $entry.name -or $entry.name -notmatch '^poc-[A-Za-z0-9-]+$') { throw "Out-of-root target: $target" }
    if (@($record.keep | Where-Object { $_.path -eq $target }).Count -gt 0) { throw 'Keep/remove overlap' }
    $resolved = (Resolve-Path -LiteralPath $target).Path
    if ($resolved -ne $target) { throw 'Resolved target mismatch' }
    $manifest = Join-Path $target 'package.json'
    if ((Get-FileHash -LiteralPath $manifest -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.manifest_sha256) { throw 'Package manifest changed after planning' }
    $metadata = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
    if ($metadata.format -notin @('second-sight-local-test-v1','second-sight-local-test-v2') -or $metadata.status -ne 'awaiting-user-runtime-test') { throw 'Unknown package' }
    $exe = Join-Path $target 'game\secondsight.EXE'
    if ((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $metadata.files.'game/secondsight.EXE') { throw 'Package EXE identity changed' }
    foreach ($process in Get-CimInstance Win32_Process -Filter "Name='secondsight.exe'") {
        if (-not $process.ExecutablePath) { throw 'Running game path is unknown; pruning stopped' }
        if ($process.ExecutablePath.StartsWith($target + '\',[StringComparison]::OrdinalIgnoreCase)) { throw "Test copy is in use: $target" }
    }
    $targets += $target
}
# Every absolute target is checked above before any recursive removal begins.
foreach ($target in $targets) {
    $bytes = (Get-ChildItem -LiteralPath $target -Recurse -File -Force | Measure-Object Length -Sum).Sum
    Remove-Item -LiteralPath $target -Recurse -Force
    if (Test-Path -LiteralPath $target) { throw 'Removal incomplete' }
    Write-Output "PRUNE PASS: removed=$target; bytes=$bytes"
}
foreach ($entry in $record.keep) {
    if (-not (Test-Path -LiteralPath (Join-Path $entry.path 'package.json'))) { throw 'Retained package missing' }
}
