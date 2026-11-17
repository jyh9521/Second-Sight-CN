"""Stage an isolated local test copy, never launch it and never change the source."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from assess_resources import require
from build_locale import ROOT, EXE_SHA, build

FUSION_FILES = {
    "dinput8.dll":"63b465dbc1bf9c5ab4e33c3ccad099d9edb702f2c51587ac8d4f196497396437",
    "scripts/SecondSight.FusionFix.asi":"939d0bbc6dacca73b4323fa018ba11d04a87dde5073e795b5914db85d6158430",
    "scripts/SecondSight.FusionFix.cfg":"a05007595a84708d4973785e5ef690f6d95901484af3542c00045d2f5f49c826",
}

def sha(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file,"sha256").hexdigest()


def inventory(path: Path) -> dict:
    return {p.relative_to(path).as_posix():sha(p) for p in sorted(path.rglob("*")) if p.is_file()}


def verify(out: Path) -> None:
    record=json.loads((out/"package.json").read_text(encoding="utf-8"))
    require(record["format"]=="second-sight-local-test-v1", "not a test package")
    for name,expected in record["files"].items():
        path=(out/name).resolve()
        require(path.is_relative_to(out.resolve()), "package path escapes root")
        require(sha(path)==expected, f"package file changed: {name}")
    require(sha(out/"game/secondsight.EXE")==EXE_SHA,"game EXE changed")
    for name,expected in FUSION_FILES.items():
        require(sha(out/"game"/name)==expected,f"FusionFix changed: {name}")
    print(f"PACKAGE PASS: files={len(record['files'])}; original EXE; pinned FusionFix; independent ASI; runtime=PENDING")


def stage(game: Path, fusionfix: Path, out: Path, locale: str) -> None:
    game,fusionfix,out=game.resolve(),fusionfix.resolve(),out.resolve()
    require(not out.exists(),"choose a new output directory; existing output is not overwritten")
    require(not out.is_relative_to(game) and not game.is_relative_to(out),"output overlaps original game")
    require(sha(game/"secondsight.EXE")==EXE_SHA,"unsupported executable")
    for name,expected in FUSION_FILES.items():
        require(sha(fusionfix/name)==expected,f"unsupported FusionFix input: {name}")
    before=inventory(game)
    locale_dir=ROOT/"build"/f"locale-{locale}"
    build(game,locale,locale_dir)
    subprocess.run(["powershell","-NoProfile","-ExecutionPolicy","Bypass","-File",str(ROOT/"tools/build_runtime.ps1")],check=True,cwd=ROOT)
    runtime=ROOT/"build/runtime"
    subprocess.run([str(runtime/"localization_host.exe"),str(runtime/"SecondSight.Localization.asi"),str(locale_dir/"locale.bin")],check=True,cwd=ROOT)
    target=out/"game"
    target.mkdir(parents=True)
    for folder in ("pak","win32","trailers"):
        shutil.copytree(game/folder,target/folder)
    (target/"profiles").mkdir() # fresh local profile; original save files are not copied or changed
    for name in ("secondsight.EXE","secondsight.cfg"):
        shutil.copy2(game/name,target/name)
    for name in FUSION_FILES:
        destination=target/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(fusionfix/name,destination)
    shutil.copy2(runtime/"SecondSight.Localization.asi",target/"scripts/SecondSight.Localization.asi")
    translated=target/"scripts/localization"
    translated.mkdir()
    for name in ("locale.bin","manifest.json","OFL.txt"):
        shutil.copy2(locale_dir/name,translated/name)
    shutil.copy2(ROOT/"LICENSE",translated/"LICENSE-code.txt")
    shutil.copy2(ROOT/"assets/FONT-NOTICE.txt",translated/"FONT-NOTICE.txt")
    if (ROOT/"docs/POC_TESTING.md").exists():
        shutil.copy2(ROOT/"docs/POC_TESTING.md",out/"TESTING.md")
    disable='''# Does not start or stop the game. Run only after manually closing the test game.
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($PSScriptRoot)
$asi = Join-Path $root 'game\\scripts\\SecondSight.Localization.asi'
$disabled = "$asi.disabled"
if (Test-Path -LiteralPath $disabled) { throw 'Already disabled, or target exists' }
$manifest = Get-Content -LiteralPath (Join-Path $root 'package.json') -Raw | ConvertFrom-Json
$expected = $manifest.files.'game/scripts/SecondSight.Localization.asi'
if ((Get-FileHash -LiteralPath $asi -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'ASI hash mismatch' }
Move-Item -LiteralPath $asi -Destination $disabled
Write-Output 'DISABLE PASS: Localization ASI disabled; FusionFix retained; no game launched'
'''
    (out/"Disable-Localization.ps1").write_text(disable,encoding="utf-8",newline="\n")
    after=inventory(game)
    require(before==after,"original game inventory changed during staging")
    (out/"source-inventory.json").write_text(json.dumps(before,indent=2)+"\n",encoding="utf-8")
    record=dict(format="second-sight-local-test-v1",locale=locale,status="awaiting-user-runtime-test",
                source=str(game),source_unchanged=True,files=inventory(out))
    (out/"package.json").write_text(json.dumps(record,indent=2)+"\n",encoding="utf-8")
    verify(out)
    print(f"STAGE PASS: {out}; original files={len(before)} unchanged; game NOT launched")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--game-root",type=Path)
    p.add_argument("--fusionfix-root",type=Path)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--locale",default="zh-CN")
    p.add_argument("--verify",action="store_true")
    args=p.parse_args()
    if args.verify: verify(args.out)
    else:
        require(args.game_root is not None and args.fusionfix_root is not None,"game and FusionFix inputs required")
        stage(args.game_root,args.fusionfix_root,args.out,args.locale)
