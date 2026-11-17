# Enable/disable the optional module in this test package only. Never launches the game.
param([ValidateSet('Enable','Disable','Status')][string]$Mode = 'Status')
$ErrorActionPreference = 'Stop'
$env:PSModulePath = (Join-Path $PSHOME 'Modules') + [IO.Path]::PathSeparator + $env:PSModulePath
$root = $PSScriptRoot
$active = Join-Path $root 'game\scripts'
$stored = Join-Path $root 'optional\gameplay-tweaks'
$names = @('SecondSight.GameplayTweaks.ini','SecondSight.GameplayTweaks.asi')
foreach ($dir in @($root,(Join-Path $root 'optional'),$stored,(Join-Path $root 'game'),$active)) {
    $item = Get-Item -LiteralPath $dir
    if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Linked or missing package directory'
    }
}
$manifest = Get-Content -LiteralPath (Join-Path $root 'package.json') -Raw | ConvertFrom-Json
function Match-File($Path,$Expected) {
    $item = Get-Item -LiteralPath $Path
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Expected) {
        throw "Optional module file mismatch: $Path"
    }
}
$present = 0
foreach ($name in $names) {
    $expected = $manifest.files."optional/gameplay-tweaks/$name"
    if ($expected -notmatch '^[0-9a-f]{64}$') { throw 'Optional module is missing from package manifest' }
    Match-File (Join-Path $stored $name) $expected
    $dst = Join-Path $active $name
    if (Test-Path -LiteralPath $dst) { Match-File $dst $expected; ++$present }
}
if ($present -eq 1) { throw 'Incomplete installation; restore matching files before retry' }
$enabled = $present -eq 2
if ($Mode -eq 'Status' -or ($Mode -eq 'Enable' -and $enabled) -or ($Mode -eq 'Disable' -and -not $enabled)) {
    if ($enabled) { Write-Output 'GAMEPLAY TWEAKS: enabled' }
    else { Write-Output 'GAMEPLAY TWEAKS: disabled' }
    return
}
$gameExe = Join-Path $root 'game\secondsight.EXE'
foreach ($process in (Get-Process -Name secondsight -ErrorAction SilentlyContinue)) {
    if (-not $process.Path -or $process.Path -ieq $gameExe) { throw 'Close the test game before changing the module' }
}
$changed = @()
try {
    if ($Mode -eq 'Enable') {
        foreach ($name in $names) {
            $src = Join-Path $stored $name
            $dst = Join-Path $active $name
            [IO.File]::Copy($src,$dst,$false)
            $changed += $name
            Match-File $dst $manifest.files."optional/gameplay-tweaks/$name"
        }
    } else {
        foreach ($name in @($names[1],$names[0])) {
            Remove-Item -LiteralPath (Join-Path $active $name)
            $changed += $name
        }
    }
} catch {
    for ($i=$changed.Count-1;$i -ge 0;--$i) {
        $name = $changed[$i]
        $dst = Join-Path $active $name
        if ($Mode -eq 'Enable') { Remove-Item -LiteralPath $dst }
        else { [IO.File]::Copy((Join-Path $stored $name),$dst,$false) }
    }
    throw
}
if ($Mode -eq 'Enable') { Write-Output 'GAMEPLAY TWEAKS: enabled' }
else { Write-Output 'GAMEPLAY TWEAKS: disabled' }
