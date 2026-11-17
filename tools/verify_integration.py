"""Record offline loader-route checks and reversible HD disable on a separate copy."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
from stage_poc import ROOT, EXE_SHA, FUSION_FILES, REMASTER_DLL_SHA, sha, require, verify, inventory

COPY_FILES=("game/dinput8.dll","game/dsound.dll","game/scripts/SecondSight.FusionFix.asi",
            "game/scripts/SecondSight.Localization.asi","game/scripts/localization/locale.bin",
            "Set-HD.ps1","package.json")


def prepare(out: Path,baseline: Path,package: Path) -> None:
    # Windows CI TEMP may use an 8.3 alias: compare canonical paths on both sides.
    root=ROOT.resolve()
    out,baseline,package=out.resolve(),baseline.resolve(),package.resolve()
    require(out.is_relative_to(root/"build"),"evidence must be under build")
    require(not (out/"integration.json").exists(),"choose a fresh evidence directory")
    for name in ("MODIFIED_FILE.json","DIFF_FILE.json","VERIFICATION.txt","ROLLBACK.sh","rollback-copy"):
        require(not (out/name).exists(),f"existing evidence must not be overwritten: {name}")
    for path in (baseline,package):
        require(path.parent==root/"dist","package must be under dist")
    out.mkdir(parents=True,exist_ok=True)
    old=json.loads((baseline/"package.json").read_text(encoding="utf-8"))
    new=json.loads((package/"package.json").read_text(encoding="utf-8"))
    require(new["loader"]=="dsound.dll" and new["remastered"],"expected integrated HD package")
    observed=inventory(baseline)
    (out/"integration.json").write_text(json.dumps(dict(baseline=str(baseline.resolve()),package=str(package.resolve()),baseline_observed=observed),indent=2)+"\n",encoding="utf-8")
    shutil.copy2(package/"package.json",out/"MODIFIED_FILE.json")
    delta=dict(changed_fields={"loader":{"before":"dinput8.dll","after":"dsound.dll"},
                              "remastered":{"before":None,"after":new["remastered"]}},
               original_loader_sha256=old["files"]["game/dinput8.dll"],
               renamed_loader_sha256=new["files"]["game/dsound.dll"],
               remastered_proxy_sha256=new["files"]["game/dinput8.dll"],
               baseline_manifest_drift={name:dict(manifest=value,observed=observed.get(name))
                                        for name,value in old["files"].items() if observed.get(name)!=value},
               added=sorted(set(new["files"])-set(old["files"])),
               changed=sorted(k for k in old["files"].keys()&new["files"].keys() if old["files"][k]!=new["files"][k]))
    (out/"DIFF_FILE.json").write_text(json.dumps(delta,indent=2)+"\n",encoding="utf-8")
    fixture=out/"rollback-copy"
    for name in COPY_FILES:
        dest=fixture/name;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(package/name,dest)
    # This is a tiny DLL/data fixture with no game EXE, not another game test package.
    relative_root=shlex.quote(os.path.relpath(root,out).replace("\\","/"))
    script='''#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"/'''+relative_root+'''
python -X utf8 tools/verify_integration.py rollback --out '''+shlex.quote(out.relative_to(root).as_posix())+'''
'''
    (out/"ROLLBACK.sh").write_text(script,encoding="utf-8",newline="\n")
    os.chmod(out/"ROLLBACK.sh",0o755)
    print("PREPARE PASS: four-artifact evidence setup; isolated rollback copy has no game EXE")


def check(mode: str,out: Path) -> None:
    data=json.loads((out/"integration.json").read_text(encoding="utf-8"))
    package=Path(data["package"])
    baseline=Path(data["baseline"])
    if mode=="baseline":
        # The retained user's configuration is not reset to its historical manifest.
        require(inventory(baseline)==data["baseline_observed"],"retained baseline changed after snapshot")
        require(sha(baseline/"game/secondsight.EXE")==EXE_SHA,"baseline EXE changed")
        for name,value in FUSION_FILES.items():
            if name.endswith(".cfg"): continue
            require(sha(baseline/"game"/name)==value,"baseline loader/ASI changed")
        old=json.loads((baseline/"package.json").read_text(encoding="utf-8"))
        for name in ("game/scripts/SecondSight.Localization.asi","game/scripts/localization/locale.bin"):
            require(sha(baseline/name)==old["files"][name],"baseline localization changed")
        require(not (baseline/"game/Remaster_Textures").exists(),"baseline already contains HD")
        print("BASELINE PASS: UAL=dinput8.dll; HD=absent; FusionFix+localization present; observed user config preserved")
    elif mode=="modified":
        verify(package)
        require(sha(package/"package.json")==sha(out/"MODIFIED_FILE.json"),"snapshot changed")
        print("MODIFIED PASS: UAL=dsound.dll; HD=dinput8.dll; DDS=5110; runtime=PENDING")
    elif mode=="rollback":
        fixture=out/"rollback-copy"
        require(not (fixture/"game/secondsight.EXE").exists(),"rollback fixture must not contain game")
        subprocess.run(["powershell","-NoProfile","-ExecutionPolicy","Bypass","-File",str(fixture/"Set-HD.ps1"),"-Mode","disable"],check=True)
        require(not (fixture/"game/dinput8.dll").exists(),"HD proxy still active")
        require(sha(fixture/"game/dinput8.dll.disabled")==REMASTER_DLL_SHA,"HD bytes changed")
        require(sha(fixture/"game/dsound.dll")==FUSION_FILES["dinput8.dll"],"UAL changed")
        for name in COPY_FILES[2:5]:
            require(sha(fixture/name)==sha(package/name),f"retained component changed: {name}")
        require(sha(package/"game/dinput8.dll")==REMASTER_DLL_SHA,"delivered HD package changed")
        print("ROLLBACK PASS: separate copy HD=disabled; FusionFix+localization retained; delivered package HD=enabled; runtime=PENDING")


def evidence(out: Path) -> None:
    git_bash=Path(os.environ.get("ProgramFiles","C:/Program Files"))/"Git/bin/bash.exe"
    bash=str(git_bash) if git_bash.is_file() else shutil.which("bash")
    require(bash is not None,"Git Bash required to execute ROLLBACK.sh")
    runs=[]
    for mode in ("baseline","modified","rollback"):
        command=([sys.executable,"-X","utf8","tools/verify_integration.py",mode,"--out",str(out)]
                 if mode!="rollback" else [bash,str(out/"ROLLBACK.sh")])
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding="utf-8",errors="replace")
        runs.append(dict(mode=mode,command=command,input=str(out/"integration.json"),
                         stdout=result.stdout,stderr=result.stderr,exit_status=result.returncode))
        print(result.stdout,end="",flush=True)
        if result.returncode: print(result.stderr,flush=True)
    passed=all(row["exit_status"]==0 for row in runs)
    lines=["OFFLINE INTEGRATION VERIFICATION", "changed fields: loader=dinput8.dll -> dsound.dll; remastered=null -> pinned DDS input",
           "Original DLL hashes are preserved in DIFF_FILE.json; MODIFIED_FILE.json is the delivered package manifest.",
           ("Restored status: separate fixture HD disabled; FusionFix/localization retained. Delivered package remains HD enabled."
            if passed else "Verification incomplete: review failed checks below before accepting this record."),
           "Game runtime behavior is PENDING user testing; no game was launched.","",
           *[f"{name}: {(out/name).resolve()}" for name in ("MODIFIED_FILE.json","DIFF_FILE.json","VERIFICATION.txt","ROLLBACK.sh")],""]
    for row in runs:
        lines += [row["mode"].upper(),"command: "+subprocess.list2cmdline(row["command"]),
                  "cwd: "+str(ROOT),"input: "+row["input"],"stdout:",row["stdout"],"stderr:",row["stderr"],
                  "exit_status: "+str(row["exit_status"]),""]
    (out/"VERIFICATION.txt").write_text("\n".join(lines),encoding="utf-8")
    require(passed,"integration evidence contains failed checks")
    # Reopen every claimed artifact.
    for name in ("MODIFIED_FILE.json","DIFF_FILE.json","VERIFICATION.txt","ROLLBACK.sh"):
        require(bool((out/name).read_bytes()),f"empty evidence file: {name}")
    print("EVIDENCE PASS: BASELINE=0 MODIFIED=0 ROLLBACK=0; four artifacts reopened; no game launched")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("prepare","baseline","modified","rollback","evidence"))
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--baseline",type=Path)
    parser.add_argument("--package",type=Path)
    args=parser.parse_args()
    if args.mode=="prepare": prepare(args.out.resolve(),args.baseline.resolve(),args.package.resolve())
    elif args.mode=="evidence": evidence(args.out.resolve())
    else: check(args.mode,args.out.resolve())
