# Only toggles files in the package containing this script. Never starts/stops a game.
param([Parameter(Mandatory=$true)][ValidateSet('disable','enable')][string]$Mode)
$ErrorActionPreference = 'Stop'
$env:PSModulePath = (Join-Path $PSHOME 'Modules') + [IO.Path]::PathSeparator + $env:PSModulePath
$root = [IO.Path]::GetFullPath($PSScriptRoot)
$manifest = Get-Content -LiteralPath (Join-Path $root 'package.json') -Raw | ConvertFrom-Json
if ($manifest.format -ne 'second-sight-local-test-v2' -or $manifest.loader -ne 'dsound.dll' -or -not $manifest.remastered) { throw 'Not a dsound HD test package' }
$game = Join-Path $root 'game'
foreach ($folder in @($root,$game)) {
    if ((Get-Item -LiteralPath $folder -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked package path rejected' }
}
$active = Join-Path $game 'dinput8.dll'
$inactive = Join-Path $game 'dinput8.dll.disabled'
if ($Mode -eq 'disable') { $source=$active; $destination=$inactive } else { $source=$inactive; $destination=$active }
if (Test-Path -LiteralPath $destination) { throw 'Destination exists; no overwrite performed' }
if ((Get-Item -LiteralPath $source -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked DLL rejected' }
if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.files.'game/dinput8.dll') { throw 'ReMade DLL hash mismatch' }
if ((Get-FileHash -LiteralPath (Join-Path $game 'dsound.dll') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.files.'game/dsound.dll') { throw 'UAL hash mismatch' }
Move-Item -LiteralPath $source -Destination $destination
Write-Output "HD TOGGLE PASS: mode=$Mode; ReMade bytes preserved; UAL/FusionFix/localization retained; no game launched"
