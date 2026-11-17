"""Evidence and copy-only rollback for the generated PDA translations."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from assess_resources import require
from build_locale import ROOT,EXE_SHA,PDA_SHA,digest,decode
from pda_resources import PdaResource


def prepare(game: Path, locale_build: Path, out: Path) -> None:
    require(not out.exists(),"evidence output already exists")
    out.mkdir(parents=True)
    for source,destination in (("BASELINE.raw","BASELINE.raw"),("MODIFIED_FILE.raw","MODIFIED_FILE.raw"),("manifest.json","locale-manifest.json")):
        shutil.copy2(locale_build/source,out/destination)
    a=PdaResource((out/"BASELINE.raw").read_bytes()); b=PdaResource((out/"MODIFIED_FILE.raw").read_bytes())
    changes=[dict(id=k,field=hex(v.field_offset),old_pointer=hex(v.value),new_pointer=hex(b.segments[k].value))
             for k,v in a.segments.items() if v.text!=b.segments[k].text]
    manifest=json.loads((out/"locale-manifest.json").read_text(encoding="utf-8"))
    require({x['id'] for x in changes}==set(manifest['pda_ids']),"PDA changes differ from build manifest")
    require(set(manifest['targets']['pda'])==set(manifest['pda_ids']),"missing frozen PDA targets")
    data=dict(source_executable=str((game/"secondsight.EXE").resolve()),source_executable_sha256=EXE_SHA,
              baseline_sha256=digest(a.data),modified_sha256=digest(b.data),fields=changes,
              runtime_branches=["BS 0x43E663","PDA 0x583BB5","font mode 0x611885","six marker comparisons 0x2C -> 0x1F",
                                "PDA word 0x58074D","PDA skip 0x580832","PDA expand 0x580C2A/0x580C4C","key expansion 0x610260"],
              state="offline-verified; user runtime acceptance pending")
    (out/"DIFF_FILE.json").write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8")
    script=Path(__file__).resolve().as_posix()
    rollback='#!/usr/bin/env bash\nset -euo pipefail\nHERE="$(cd -- "$(dirname -- "$0")" && pwd)"\n'
    rollback+='if [ "$#" -ne 1 ]; then echo "Usage: ROLLBACK.sh TARGET_COPY" >&2; exit 2; fi\n'
    rollback+=f'exec python -X utf8 "{script}" restore --out "$HERE" --target "$1"\n'
    (out/"ROLLBACK.sh").write_text(rollback,encoding="utf-8",newline="\n");(out/"ROLLBACK.sh").chmod(0o755)
    shutil.copy2(out/"MODIFIED_FILE.raw",out/"ROLLBACK_TEST.raw")
    print(f"PREPARE PASS: {len(changes)}-field PDA evidence; original preserved; modified copy retained")


def check(stage: str,out: Path,target: Path|None=None) -> None:
    metadata=json.loads((out/"DIFF_FILE.json").read_text(encoding="utf-8"))
    locale=json.loads((out/"locale-manifest.json").read_text(encoding="utf-8"))
    original=(out/"BASELINE.raw").read_bytes(); changed=(out/"MODIFIED_FILE.raw").read_bytes()
    require(digest(Path(metadata["source_executable"]).read_bytes())==EXE_SHA,"original executable changed")
    require(digest(original)==metadata["baseline_sha256"]==PDA_SHA,"baseline hash mismatch")
    require(digest(changed)==metadata["modified_sha256"],"modified hash mismatch")
    a,b=PdaResource(original),PdaResource(changed)
    if stage=="baseline":
        require(a.replace({})==original,"baseline roundtrip differs")
        require(a.segments["p055.r003.s000"].text==b"Get out of the isolation cell.","baseline source text differs")
        print("BASELINE PASS: PDA=79622 bytes; roundtrip=identical; objective=Get out of the isolation cell.; original EXE unchanged")
    elif stage=="modified":
        expected=locale['targets']['pda']
        expected_ids=set(expected)
        require({k for k,v in a.segments.items() if v.text!=b.segments[k].text}==expected_ids,"unexpected text change")
        for key,target_text in expected.items():
            require(decode(b.segments[key].text,locale["glyphs"])==target_text,"target decoding mismatch")
        fields={a.segments[k].field_offset+j for k in expected_ids for j in range(4)}
        require(all(x==changed[i] for i,x in enumerate(original) if i not in fields),"unrelated original bytes changed")
        require(a.identifiers==b.identifiers,"machine identifiers changed")
        print(f"MODIFIED PASS: PDA fields={len(expected_ids)}; all targets decoded; unrelated bytes=unchanged; runtime=PENDING")
    elif stage=="restore":
        require(target is not None and target.resolve()==(out/"ROLLBACK_TEST.raw").resolve(),"restore only accepts designated test copy")
        require(target.read_bytes()==changed,"rollback target not expected modified copy")
        target.write_bytes(original)
        require(target.read_bytes()==original,"restored bytes differ")
        print("RESTORE PASS: isolated ROLLBACK_TEST.raw restored byte-for-byte; modified artifact retained")
    elif stage=="rollback":
        require((out/"ROLLBACK_TEST.raw").read_bytes()==original,"rollback differs")
        print("ROLLBACK PASS: original PDA bytes/text restored; MODIFIED_FILE.raw retained; original EXE unchanged")


def evidence(out: Path) -> None:
    relative=out.relative_to(ROOT).as_posix() if out.is_relative_to(ROOT) else out.as_posix()
    commands=[
        [sys.executable,"-X","utf8","tools/verify_poc.py","baseline","--out",relative],
        [sys.executable,"-X","utf8","tools/verify_poc.py","modified","--out",relative],
        [r"C:\Program Files\Git\bin\bash.exe",f"{relative}/ROLLBACK.sh",f"{relative}/ROLLBACK_TEST.raw"],
        [sys.executable,"-X","utf8","tools/verify_poc.py","rollback","--out",relative],
    ]
    metadata=json.loads((out/'DIFF_FILE.json').read_text(encoding='utf-8'))
    result=["Second Sight PoC offline verification",f"cwd={ROOT}",
            f"changed fields: {len(metadata['fields'])} PDA pointer fields enumerated in DIFF_FILE.json; runtime BS/PDA pointer adapters and native glyph marker/mode branches",
            "input: baseline user-supplied PDA; modified catalog translations; rollback a second modified copy",
            "Runtime acceptance: PENDING; no game process launched by these commands"]
    result.append('related runtime branches: '+', '.join(metadata['runtime_branches']))
    for name in ("MODIFIED_FILE.raw","DIFF_FILE.json","VERIFICATION.txt","ROLLBACK.sh"):
        result.append(f"{name}={out/name}")
    for command in commands:
        p=subprocess.run(command,cwd=ROOT,text=True,encoding="utf-8",capture_output=True)
        result.extend(["",f"COMMAND: {subprocess.list2cmdline(command)}",f"EXIT: {p.returncode}","STDOUT:",p.stdout.rstrip(),"STDERR:",p.stderr.rstrip()])
        require(p.returncode==0,p.stdout+p.stderr)
    (out/"VERIFICATION.txt").write_text("\n".join(result)+"\n",encoding="utf-8")
    for name in ("MODIFIED_FILE.raw","DIFF_FILE.json","VERIFICATION.txt","ROLLBACK.sh"):
        require(bool((out/name).read_bytes()),f"artifact reopen failed: {name}")
    print("EVIDENCE PASS: baseline, modified, rollback exit=0; four artifacts reopened; runtime=PENDING")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage",choices=["prepare","baseline","modified","restore","rollback","evidence"])
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--game-root",type=Path)
    p.add_argument("--locale-build",type=Path)
    p.add_argument("--target",type=Path)
    args=p.parse_args();args.out=args.out.resolve()
    if args.stage=="prepare": prepare(args.game_root,args.locale_build,args.out)
    elif args.stage=="evidence": evidence(args.out)
    else: check(args.stage,args.out,args.target)
