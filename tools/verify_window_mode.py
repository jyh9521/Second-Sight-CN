"""Reproduce the package's borderless config change and rollback on data only."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from assess_resources import require
from stage_poc import BORDERLESS_CONFIG_SHA, FUSION_CONFIG_PATH, FUSION_FILES, ROOT, write_fusionfix_config


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare(source: Path, out: Path) -> None:
    before=source.read_bytes()
    require(digest(before)==FUSION_FILES[FUSION_CONFIG_PATH],"unsupported baseline config")
    require(not out.exists(),"choose a new evidence directory")
    out.mkdir(parents=True)
    (out/"BASELINE.cfg").write_bytes(before)
    write_fusionfix_config(source,out/"MODIFIED_FILE.cfg")
    after=(out/"MODIFIED_FILE.cfg").read_bytes()
    differences=[dict(offset=i,before=a,after=b) for i,(a,b) in enumerate(zip(before,after)) if a!=b]
    require(len(before)==len(after) and len(differences)==1,"expected exactly one changed byte")
    record=dict(field="MAIN.WindowMode",before=0,after=2,source_sha256=digest(before),
                modified_sha256=digest(after),differences=differences)
    (out/"DIFF_FILE.json").write_text(json.dumps(record,indent=2)+"\n",encoding="utf-8",newline="\n")
    (out/"ROLLBACK_TEST.cfg").write_bytes(after)
    tool=ROOT/"tools/verify_window_mode.py"
    try:
        reference=Path(os.path.relpath(tool,out)).as_posix()
    except ValueError:
        # Windows has no relative path between volumes (e.g. CI D: repo/C: temp).
        reference=tool.as_posix()
    script='#!/usr/bin/env bash\nset -euo pipefail\ncd -- "$(dirname -- "$0")"\nexec python -X utf8 '+shlex.quote(reference)+' rollback --out .\n'
    (out/"ROLLBACK.sh").write_text(script,encoding="utf-8",newline="\n")
    (out/"ROLLBACK.sh").chmod(0o755)
    require(source.read_bytes()==before,"input config changed")
    print("PREPARE PASS: one config byte changed; source retained; separate rollback copy; no game execution")


def probe(path: Path) -> int:
    value=digest(path.read_bytes())
    require(value in (FUSION_FILES[FUSION_CONFIG_PATH],BORDERLESS_CONFIG_SHA),"unknown config bytes")
    mode=2 if value==BORDERLESS_CONFIG_SHA else 0
    print(f"WINDOW {'PASS' if mode==2 else 'FAIL'}: MAIN.WindowMode={mode}; required=2; no game execution")
    return 0 if mode==2 else 2


def rollback(out: Path) -> None:
    baseline=(out/"BASELINE.cfg").read_bytes()
    modified=(out/"MODIFIED_FILE.cfg").read_bytes()
    target=out/"ROLLBACK_TEST.cfg"
    require(not target.is_symlink(),"linked rollback target rejected")
    require(digest(baseline)==FUSION_FILES[FUSION_CONFIG_PATH],"baseline hash mismatch")
    require(digest(modified)==BORDERLESS_CONFIG_SHA,"modified hash mismatch")
    require(target.read_bytes()==modified,"rollback copy is not the expected modified config")
    target.write_bytes(baseline)
    require(target.read_bytes()==baseline,"rollback mismatch")
    require((out/"MODIFIED_FILE.cfg").read_bytes()==modified,"modified artifact changed")
    print("ROLLBACK PASS: separate config restored byte-for-byte to WindowMode=0; modified config remains WindowMode=2; no game execution")


def evidence(out: Path) -> None:
    out=out.resolve()
    script=str(Path(__file__).resolve())
    bash=shutil.which("bash")
    if os.name=="nt":
        candidate=Path(os.environ.get("ProgramFiles","C:/Program Files"))/"Git/bin/bash.exe"
        if candidate.is_file(): bash=str(candidate)
    require(bash is not None,"Git Bash is required for the rollback evidence")
    records=[("BASELINE",[sys.executable,"-X","utf8",script,"probe","--file",str(out/"BASELINE.cfg")],2,out/"BASELINE.cfg"),
             ("MODIFIED",[sys.executable,"-X","utf8",script,"probe","--file",str(out/"MODIFIED_FILE.cfg")],0,out/"MODIFIED_FILE.cfg"),
             ("ROLLBACK",[bash,str(out/"ROLLBACK.sh")],0,out/"ROLLBACK_TEST.cfg")]
    lines=["OFFLINE BORDERLESS CONFIG VERIFICATION", "Changed field: MAIN.WindowMode 0 -> 2; offset 330; no binary changes.",
           "Runtime: pending user test; the new EXE+0x135FC crash is not claimed fixed."]
    for name in ("MODIFIED_FILE.cfg","DIFF_FILE.json","VERIFICATION.txt","ROLLBACK.sh"):
        lines.append(f"{name}: {out/name}")
    for name,command,expected,path in records:
        result=subprocess.run(command,capture_output=True,text=True,encoding="utf-8",cwd=ROOT)
        lines.extend(["",name,"command: "+subprocess.list2cmdline(command),"input: "+str(path),
                      "stdout:",result.stdout,"stderr:",result.stderr,f"exit_status: {result.returncode}",f"expected_exit_status: {expected}"])
        (out/"VERIFICATION.txt").write_text("\n".join(lines)+"\n",encoding="utf-8",newline="\n")
        require(result.returncode==expected,f"{name} unexpected exit status")
    lines.append("Restored: independent config copy has original hash and WindowMode=0; modified artifact/package remains borderless; gameplay status unverified.")
    (out/"VERIFICATION.txt").write_text("\n".join(lines)+"\n",encoding="utf-8",newline="\n")
    print("EVIDENCE PASS: baseline=2; modified=0; rollback=0; game not launched")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("prepare");p.add_argument("--source",type=Path,required=True);p.add_argument("--out",type=Path,required=True)
    p=sub.add_parser("probe");p.add_argument("--file",type=Path,required=True)
    for name in ("rollback","evidence"):
        p=sub.add_parser(name);p.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    if args.command=="prepare": prepare(args.source,args.out)
    elif args.command=="probe": sys.exit(probe(args.file))
    elif args.command=="rollback": rollback(args.out)
    else: evidence(args.out)
