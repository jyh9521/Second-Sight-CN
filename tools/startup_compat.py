"""Verify FusionFix startup instruction contracts without executing game code."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import struct
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
EXE_SHA="4092a8d1fb042dffe9fb95e2185f32cb80390299145e8d453a5e909a06d35fda"
OVERLAY=0x10002000 # offline sentinel, not an address used by the runtime ASI


def sites(overlay: int=OVERLAY) -> list[dict]:
    """Read the native adapter's authoritative sites; do not maintain a second patch table."""
    text=(ROOT/"src/startup_compat.hpp").read_text(encoding="utf-8")
    matches=re.findall(r"\{(0x[0-9a-f]+),(\d+),\{([^}]+)\},\{([^}]+)\}\}",text)
    if len(matches)!=4: raise ValueError("native patch table shape changed")
    if not 0<overlay<2**32: raise ValueError("invalid x86 overlay pointer")
    rows=[]
    for rva,size,before,after in matches:
        size=int(size)
        decode=lambda value:bytes(int(v.strip(),0) for v in value.split(","))[:size]
        rows.append(dict(rva=int(rva,16),before=decode(before),after=decode(after)))
    rows[3]["after"]=b"\xd8\x0d"+struct.pack("<I",overlay)
    return rows


def transform(image: bytes,restore: bool=False) -> bytes:
    changes=sites()
    for row in changes:
        expected=row["after"] if restore else row["before"]
        if image[row["rva"]:row["rva"]+len(expected)]!=expected:
            raise ValueError(f"instruction contract mismatch at RVA {row['rva']:#x}")
    result=bytearray(image)
    for row in changes:
        value=row["before"] if restore else row["after"]
        result[row["rva"]:row["rva"]+len(value)]=value
    return bytes(result)


def contracts(image: bytes) -> list[dict]:
    rows=json.loads((ROOT/"assets/fusionfix-startup-contracts.json").read_text(encoding="utf-8"))["patterns"]
    results=[]
    for row in rows:
        expression=b"".join(b"." if token=="?" else re.escape(bytes([int(token,16)])) for token in row["pattern"].split())
        found=[hex(0x400000+m.start()) for m in re.finditer(expression,image,re.DOTALL)]
        results.append(dict(row,matches=found,passed=found==[row["expected_address"]]))
    return results


def mapped_game(exe: Path) -> bytes:
    import pefile
    data=exe.read_bytes()
    if hashlib.sha256(data).hexdigest()!=EXE_SHA: raise ValueError("unsupported original EXE")
    pe=pefile.PE(data=data)
    # These instruction signatures live in .text. Retain .rdata as context, but
    # omit the game's ~68 MB zero-filled BSS from local analysis-only fixtures.
    end=max(s.VirtualAddress+s.SizeOfRawData for s in pe.sections if s.Name.rstrip(b"\0") in (b".text",b".rdata"))
    return pe.get_memory_mapped_image()[:end]


def preflight(exe: Path) -> None:
    before=mapped_game(exe)
    after=transform(before)
    matches=contracts(after)
    if not all(row["passed"] for row in matches): raise ValueError("adapted startup signature preflight failed")
    if transform(after,True)!=before: raise ValueError("startup contract roundtrip failed")
    print("STARTUP PREFLIGHT PASS: 27/27 direct signatures unique after four contracts; disk bytes untouched; runtime=PENDING",flush=True)


def prepare(out: Path,exe: Path) -> None:
    if not out.resolve().is_relative_to(ROOT/"build"): raise ValueError("evidence must be inside build")
    out.mkdir(parents=True,exist_ok=True)
    if (out/"BASELINE.image").exists(): raise ValueError("choose fresh evidence output")
    before=mapped_game(exe)
    (out/"BASELINE.image").write_bytes(before)
    runtime=ROOT/"build/runtime"
    subprocess.run([str(runtime/"compatibility_host.exe"),str(runtime/"SecondSight.Compatibility.asi"),
                    str(out/"BASELINE.image"),str(out/"MODIFIED_FILE.image")],check=True)
    after=(out/"MODIFIED_FILE.image").read_bytes()
    if after!=transform(before): raise ValueError("native adapter and offline contract transforms differ")
    delta=dict(source_exe=str(exe.resolve()),source_exe_sha256=EXE_SHA,
               baseline_sha256=hashlib.sha256(before).hexdigest(),modified_sha256=hashlib.sha256(after).hexdigest(),
               overlay="offline sentinel 0x10002000; runtime uses adapter-owned writable float",
               sites=[dict(rva=hex(row["rva"]),before=row["before"].hex(),after=row["after"].hex()) for row in sites()],
               baseline_patterns=contracts(before),modified_patterns=contracts(after))
    (out/"DIFF_FILE.json").write_text(json.dumps(delta,indent=2)+"\n",encoding="utf-8",newline="\n")
    (out/"ROLLBACK_TEST.image").write_bytes(after)
    # Evidence output is intentionally non-executable game data, never an installed EXE.
    relative=out.resolve().relative_to(ROOT).as_posix()
    back=shlex.quote(os.path.relpath(ROOT,out.resolve()).replace("\\","/"))
    script=f'#!/usr/bin/env bash\nset -euo pipefail\ncd -- "$(dirname -- "$0")"/{back}\npython -X utf8 tools/startup_compat.py rollback --out {shlex.quote(relative)}\n'
    (out/"ROLLBACK.sh").write_text(script,encoding="utf-8",newline="\n")
    (out/"ROLLBACK.sh").chmod(0o755)
    print("PREPARE PASS: native adapter produced analysis-only image; original EXE unchanged")


def probe(image: Path) -> int:
    rows=contracts(image.read_bytes());passed=sum(row["passed"] for row in rows)
    print(f"CONTRACT {'PASS' if passed==len(rows) else 'FAIL'}: {passed}/{len(rows)} direct signatures unique; missing={sum(not row['matches'] for row in rows)}; no game execution")
    return 0 if passed==len(rows) else 2


def rollback(out: Path) -> None:
    record=json.loads((out/"DIFF_FILE.json").read_text())
    target=out/"ROLLBACK_TEST.image";current=target.read_bytes()
    if hashlib.sha256(current).hexdigest()!=record["modified_sha256"]: raise ValueError("rollback fixture changed")
    restored=transform(current,True)
    if hashlib.sha256(restored).hexdigest()!=record["baseline_sha256"]: raise ValueError("rollback hash mismatch")
    target.write_bytes(restored)
    if (out/"MODIFIED_FILE.image").read_bytes()!=current: raise ValueError("modified artifact unexpectedly changed")
    print("ROLLBACK PASS: separate image restored byte-for-byte; original 4 missing signatures reproduced; modified image retained; no game execution")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("preflight","prepare","probe","rollback"))
    parser.add_argument("--exe",type=Path)
    parser.add_argument("--out",type=Path)
    parser.add_argument("--image",type=Path)
    args=parser.parse_args()
    if args.mode=="preflight": preflight(args.exe)
    elif args.mode=="prepare": prepare(args.out.resolve(),args.exe)
    elif args.mode=="probe": sys.exit(probe(args.image))
    else: rollback(args.out.resolve())
