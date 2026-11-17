"""Stage an isolated local test copy, never launch it and never change the source."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from assess_resources import require
from build_locale import ROOT, EXE_SHA, build
from package_retention import apply_retention, assert_plain_tree, candidates, is_link, sequence
from startup_compat import preflight as startup_preflight
from fusionfix_config import borderless_config

FUSION_FILES = {
    "dinput8.dll":"63b465dbc1bf9c5ab4e33c3ccad099d9edb702f2c51587ac8d4f196497396437",
    "scripts/SecondSight.FusionFix.asi":"939d0bbc6dacca73b4323fa018ba11d04a87dde5073e795b5914db85d6158430",
    "scripts/SecondSight.FusionFix.cfg":"a05007595a84708d4973785e5ef690f6d95901484af3542c00045d2f5f49c826",
}
FUSION_CONFIG_PATH = "scripts/SecondSight.FusionFix.cfg"
# Fixed input with only MAIN.WindowMode's byte changed from 0 to 2.
BORDERLESS_CONFIG_SHA = "61bf3e1c037a57661d7df2273a58cd6ac62529bbdfd9bf5fff642e890ce5f48b"
REMASTER_DLL_SHA = "8aa884f7a6f4a4fa5294f457c0480149dc684479c9adbd8617c14c539d47f947"
REMASTER_INVENTORY_SHA = "2ee7e2b39b9e56f3c55ab396157775f18bb5adbd411aab983a654d235281da5a"
LOADER_INI = "[GlobalSets]\nLoadPlugins=1\nDontLoadFromDllMain=1\nDebugLog=1\n"
COMPAT_LOADER_INI = LOADER_INI+"LoadExtraPlugins=scripts\\SecondSight.Compatibility.asi\n"
TWEAKS_FILES = ("SecondSight.GameplayTweaks.ini","SecondSight.GameplayTweaks.asi")
TWEAKS_DIR = "optional/gameplay-tweaks"

def sha(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file,"sha256").hexdigest()


def inventory(path: Path) -> dict:
    return {p.relative_to(path).as_posix():sha(p) for p in sorted(path.rglob("*")) if p.is_file()}


def fusionfix_config_record() -> dict:
    return dict(policy="borderless-v1",overrides={"MAIN.WindowMode":2},
                source_sha256=FUSION_FILES[FUSION_CONFIG_PATH],output_sha256=BORDERLESS_CONFIG_SHA)


def write_fusionfix_config(source: Path, destination: Path) -> dict:
    data=source.read_bytes()
    require(hashlib.sha256(data).hexdigest()==FUSION_FILES[FUSION_CONFIG_PATH],"unsupported FusionFix config input")
    output=borderless_config(data)
    require(hashlib.sha256(output).hexdigest()==BORDERLESS_CONFIG_SHA,"unexpected borderless config output")
    with destination.open("xb") as file: file.write(output)
    return fusionfix_config_record()


def remastered_inventory(root: Path, hashes: dict | None = None) -> list[dict]:
    """Pin the complete assessed input, not just its proxy DLL or DDS count."""
    if hashes is None:
        assert_plain_tree(root)
        hashes=inventory(root)
    rows=[dict(path=name,size=(root/name).stat().st_size,sha256=value)
          for name,value in sorted(hashes.items(),key=lambda pair:Path(pair[0]))]
    require(len(rows)==5111,"expected exactly one ReMade DLL and 5110 textures")
    require(hashes.get("dinput8.dll")==REMASTER_DLL_SHA,"unsupported ReMade DLL")
    require(all(name=="dinput8.dll" or re.fullmatch(r"Remaster_Textures/tex_[0-9A-F]{8}\.dds",name)
                for name in hashes),"unexpected ReMade input file")
    digest=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    require(digest==REMASTER_INVENTORY_SHA,"ReMade inventory differs from assessed input")
    return rows


def validate_layout(record: dict) -> None:
    require(record.get("format") in ("second-sight-local-test-v1","second-sight-local-test-v2"),"not a test package")
    files=record["files"]
    require(files.get("game/secondsight.EXE")==EXE_SHA,"game EXE identity missing/changed")
    hd=record["format"].endswith("v2") and bool(record.get("remastered"))
    loader="dsound.dll" if hd else "dinput8.dll"
    if record["format"].endswith("v2"):
        require(record.get("loader")==loader,"unexpected loader route")
        require(record.get("status")=="awaiting-user-runtime-test","invalid package status")
        require(record.get("version")==sequence(record.get("package_id","")),"invalid package sequence")
        require(isinstance(record.get("version"),int),"missing package sequence")
    config=record.get("fusionfix_config")
    if record.get("version",0)>=4 or config is not None:
        require(config==fusionfix_config_record(),"missing/invalid pinned borderless config override")
    for name,expected in FUSION_FILES.items():
        if name==FUSION_CONFIG_PATH and config is not None: expected=BORDERLESS_CONFIG_SHA
        destination=loader if name=="dinput8.dll" else name
        require(files.get("game/"+destination)==expected,f"FusionFix identity missing/changed: {destination}")
    require("game/scripts/SecondSight.Localization.asi" in files,"localization ASI missing")
    require("game/scripts/localization/locale.bin" in files,"locale pack missing")
    if record.get("startup_compat"):
        require(record["startup_compat"]=="gog-fusionfix-contracts-v1","unknown compatibility adapter")
        require("game/scripts/SecondSight.Compatibility.asi" in files,"startup adapter missing")
        require(files.get("game/"+loader.replace(".dll",".ini"))==hashlib.sha256(COMPAT_LOADER_INI.encode()).hexdigest(),"compatibility load-first setting missing/changed")
    if record.get("gameplay_tweaks"):
        require(record["gameplay_tweaks"]=="optional-disabled-v1","unknown gameplay tweaks bundle")
        require("Set-GameplayTweaks.ps1" in files,"gameplay tweaks toggle script missing")
        for name in TWEAKS_FILES:
            require(f"{TWEAKS_DIR}/{name}" in files and f"game/scripts/{name}" not in files,
                    f"optional module must be staged outside the game: {name}")
    if hd:
        require(files.get("game/dinput8.dll")==REMASTER_DLL_SHA,"ReMade proxy identity missing/changed")
        require(record["remastered"].get("inventory_sha256")==REMASTER_INVENTORY_SHA,"unknown ReMade inventory")
        settings=COMPAT_LOADER_INI if record.get("startup_compat") else LOADER_INI
        require(files.get("game/dsound.ini")==hashlib.sha256(settings.encode()).hexdigest(),"loader settings missing/changed")


def verify(out: Path) -> None:
    assert_plain_tree(out)
    record=json.loads((out/"package.json").read_text(encoding="utf-8"))
    validate_layout(record)
    for name,expected in record["files"].items():
        require(not Path(name).is_absolute() and ".." not in Path(name).parts and ":" not in name,"invalid manifest path")
        path=(out/name).resolve()
        require(path.is_relative_to(out.resolve()), "package path escapes root")
        require(sha(path)==expected, f"package file changed: {name}")
    if record.get("gameplay_tweaks"):
        active=[out/"game"/"scripts"/name for name in TWEAKS_FILES]
        present=[p for p in active if p.exists()]
        require(not present or len(present)==len(active),"incomplete optional module installation")
        for p in present:
            require(sha(p)==record["files"][f"{TWEAKS_DIR}/{p.name}"],"active optional module changed")
        print(f"OPTIONAL TWEAKS PASS: {'enabled' if present else 'disabled'}",flush=True)
    if record.get("remastered"):
        subset={name.removeprefix("game/"):value for name,value in record["files"].items()
                if name=="game/dinput8.dll" or name.startswith("game/Remaster_Textures/")}
        remastered_inventory(out/"game",subset)
    window="borderless" if record.get("fusionfix_config") else "upstream-default"
    print(f"PACKAGE PASS: files={len(record['files'])}; original EXE; pinned FusionFix binary; independent ASI; HD={bool(record.get('remastered'))}; window={window}; runtime=PENDING",flush=True)


def validate_output(out: Path, locale: str) -> int:
    dist=ROOT/"dist"
    if dist.exists(): require(not is_link(dist),"linked dist root rejected")
    require(not out.exists(),"choose a new output directory; existing output is not overwritten")
    require(out.resolve().parent==dist.resolve(),"output must be a direct child of repository dist")
    version=sequence(out.name)
    require(version is not None and out.name==f"poc-{locale}-{version:03d}","use poc-<locale>-NNN package name")
    existing=candidates(dist)
    require(not existing or version>existing[0]["version"],"output must have a new higher sequence")
    return version


def stage(game: Path, fusionfix: Path, out: Path, locale: str, remastered: Path | None = None) -> None:
    version=validate_output(out,locale)
    game,fusionfix,out=game.resolve(),fusionfix.resolve(),out.resolve()
    remastered=remastered.resolve() if remastered else None
    for source in (game,fusionfix,remastered):
        if source:
            require(not out.is_relative_to(source) and not source.is_relative_to(out),"output overlaps input")
            assert_plain_tree(source)
    require(sha(game/"secondsight.EXE")==EXE_SHA,"unsupported executable")
    startup_preflight(game/"secondsight.EXE")
    for name,expected in FUSION_FILES.items():
        require(sha(fusionfix/name)==expected,f"unsupported FusionFix input: {name}")
    print("STAGE: hashing original game and supplied dependencies",flush=True)
    before=inventory(game)
    fusion_before=inventory(fusionfix)
    hd_before=remastered_inventory(remastered) if remastered else None
    locale_dir=ROOT/"build"/f"locale-{locale}"
    build(game,locale,locale_dir)
    subprocess.run(["powershell","-NoProfile","-ExecutionPolicy","Bypass","-File",str(ROOT/"tools/build_runtime.ps1")],check=True,cwd=ROOT)
    runtime=ROOT/"build/runtime"
    subprocess.run([str(runtime/"localization_host.exe"),str(runtime/"SecondSight.Localization.asi"),str(locale_dir/"locale.bin")],check=True,cwd=ROOT)
    subprocess.run([str(runtime/"compatibility_host.exe"),str(runtime/"SecondSight.Compatibility.asi")],check=True,cwd=ROOT)
    subprocess.run([str(runtime/"gameplay_tweaks_host.exe"),str(runtime/"SecondSight.GameplayTweaks.asi")],check=True,cwd=ROOT)
    target=out/"game"
    target.mkdir(parents=True)
    print("STAGE: copying independent game files (no links, no launch)",flush=True)
    for folder in ("pak","win32","trailers"):
        shutil.copytree(game/folder,target/folder)
    (target/"profiles").mkdir() # fresh local profile; original save files are not copied or changed
    for name in ("secondsight.EXE","secondsight.cfg"):
        shutil.copy2(game/name,target/name)
    config_record=None
    for name in FUSION_FILES:
        destination=target/("dsound.dll" if remastered and name=="dinput8.dll" else name)
        destination.parent.mkdir(parents=True,exist_ok=True)
        if name==FUSION_CONFIG_PATH:
            config_record=write_fusionfix_config(fusionfix/name,destination)
        else:
            shutil.copy2(fusionfix/name,destination)
    if remastered:
        print("STAGE: copying ReMade DLL and all 5110 DDS textures",flush=True)
        shutil.copy2(remastered/"dinput8.dll",target/"dinput8.dll")
        shutil.copytree(remastered/"Remaster_Textures",target/"Remaster_Textures")
        shutil.copy2(ROOT/"tools/Set-HD.ps1",out/"Set-HD.ps1")
        (out/"remastered-input-inventory.json").write_text(json.dumps(hd_before,indent=2)+"\n",encoding="utf-8")
    shutil.copy2(runtime/"SecondSight.Localization.asi",target/"scripts/SecondSight.Localization.asi")
    shutil.copy2(runtime/"SecondSight.Compatibility.asi",target/"scripts/SecondSight.Compatibility.asi")
    optional=out/TWEAKS_DIR
    optional.mkdir(parents=True)
    shutil.copy2(runtime/TWEAKS_FILES[1],optional/TWEAKS_FILES[1])
    labels=ROOT/"locales"/locale/"gameplay-tweaks.ini"
    # Win32 profile APIs recognize the UTF-16 LE BOM, not UTF-8.
    (optional/TWEAKS_FILES[0]).write_bytes(b"\xff\xfe"+(labels.read_text(encoding="utf-8-sig") if labels.exists()
                                  else "[Menu]\n").encode("utf-16-le"))
    shutil.copy2(ROOT/"tools/Set-GameplayTweaks.ps1",out/"Set-GameplayTweaks.ps1")
    (target/("dsound.ini" if remastered else "dinput8.ini")).write_text(COMPAT_LOADER_INI,encoding="ascii",newline="\n")
    translated=target/"scripts/localization"
    translated.mkdir()
    for name in ("locale.bin","manifest.json","OFL.txt","FONT-NOTICE.txt"):
        shutil.copy2(locale_dir/name,translated/name)
    shutil.copy2(ROOT/"LICENSE",translated/"LICENSE-code.txt")
    shutil.copy2(ROOT/("docs/INTEGRATED_TESTING.md" if remastered else "docs/POC_TESTING.md"),out/"TESTING.md")
    disable='''# Does not start or stop the game. Run only after manually closing the test game.
$ErrorActionPreference = 'Stop'
$env:PSModulePath = (Join-Path $PSHOME 'Modules') + [IO.Path]::PathSeparator + $env:PSModulePath
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
    print("STAGE: verifying source preservation and output hashes",flush=True)
    after=inventory(game)
    require(before==after,"original game inventory changed during staging")
    require(fusion_before==inventory(fusionfix),"FusionFix input changed during staging")
    if remastered:
        require(hd_before==remastered_inventory(remastered),"ReMade input changed during staging")
    (out/"source-inventory.json").write_text(json.dumps(before,indent=2)+"\n",encoding="utf-8")
    record=dict(format="second-sight-local-test-v2",package_id=out.name,version=version,
                startup_compat="gog-fusionfix-contracts-v1",
                gameplay_tweaks="optional-disabled-v1",
                fusionfix_config=config_record,
                locale=locale,status="awaiting-user-runtime-test",loader="dsound.dll" if remastered else "dinput8.dll",
                remastered=dict(inventory_sha256=REMASTER_INVENTORY_SHA,dds_count=5110) if remastered else None,
                source=str(game),source_unchanged=True,dependencies_unchanged=True,files=inventory(out))
    (out/"package.json").write_text(json.dumps(record,indent=2)+"\n",encoding="utf-8")
    verify(out)
    apply_retention(ROOT,out,ROOT/"build/package-retention"/out.name)
    print(f"STAGE PASS: {out}; original files={len(before)} unchanged; game NOT launched")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--game-root",type=Path)
    p.add_argument("--fusionfix-root",type=Path)
    p.add_argument("--remastered-root",type=Path,help="optional, exact assessed ReMade input")
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--locale",default="zh-CN")
    p.add_argument("--verify",action="store_true")
    args=p.parse_args()
    if args.verify: verify(args.out)
    else:
        require(args.game_root is not None and args.fusionfix_root is not None,"game and FusionFix inputs required")
        stage(args.game_root,args.fusionfix_root,args.out,args.locale,args.remastered_root)
