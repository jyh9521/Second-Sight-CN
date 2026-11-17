param([string]$Out = "build/runtime")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$output = [IO.Path]::GetFullPath((Join-Path $root $Out))
New-Item -ItemType Directory -Force -Path $output | Out-Null
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vs = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw "MSVC x86 build tools not found" }
$vcvars = Join-Path $vs 'VC\Auxiliary\Build\vcvars32.bat'
$build = @"
@echo off
call "$vcvars" >nul
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /W4 /WX /O2 /MT /EHsc /LD /utf-8 /Brepro "$root\src\localization.cpp" /link /DEF:"$root\src\localization.def" /OUT:"$output\SecondSight.Localization.asi" /MAP:"$output\SecondSight.Localization.map" /INCREMENTAL:NO /Brepro advapi32.lib
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /W4 /WX /O2 /MT /EHsc /utf-8 /Brepro "$root\tests\localization_host.cpp" /link /OUT:"$output\localization_host.exe" /INCREMENTAL:NO /Brepro
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /W4 /WX /O2 /MT /EHsc /LD /utf-8 /Brepro "$root\src\startup_compat.cpp" /link /DEF:"$root\src\startup_compat.def" /OUT:"$output\SecondSight.Compatibility.asi" /INCREMENTAL:NO /Brepro advapi32.lib
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /W4 /WX /O2 /MT /EHsc /utf-8 /Brepro "$root\tests\compatibility_host.cpp" /link /OUT:"$output\compatibility_host.exe" /INCREMENTAL:NO /Brepro
exit /b %errorlevel%
"@
[IO.File]::WriteAllText((Join-Path $output 'compile.cmd'),$build,[Text.Encoding]::ASCII)
Push-Location $output
try { & $env:ComSpec /d /c (Join-Path $output 'compile.cmd'); if ($LASTEXITCODE -ne 0) { throw "MSVC failed: $LASTEXITCODE" } }
finally { Pop-Location }
Write-Output "BUILD PASS: localization + compatibility x86 ASIs and offline hosts; game not launched"
