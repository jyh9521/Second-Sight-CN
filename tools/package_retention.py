"""Plan retention of the latest two recognized, completed local test packages.

Deletion is delegated exclusively to the checked PowerShell implementation.
Unrecognized folders, symlinks/junctions, inputs, and research outputs are not candidates.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess
import shutil

KEEP = 2
FORMATS = {"second-sight-local-test-v1", "second-sight-local-test-v2"}


def require(condition: bool, message: str) -> None:
    if not condition: raise ValueError(message)


def is_link(path: Path) -> bool:
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info,"st_file_attributes",0)&stat.FILE_ATTRIBUTE_REPARSE_POINT)


def assert_plain_tree(root: Path) -> None:
    require(not is_link(root),f"linked package path rejected: {root}")
    for child in root.iterdir():
        require(not is_link(child),f"linked package entry rejected: {child}")
        if child.is_dir(): assert_plain_tree(child)


def sequence(name: str) -> int | None:
    if name == "poc-zh-CN": return 0 # historical unnumbered test package
    match = re.fullmatch(r"poc-[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*-(\d{3,})",name)
    return int(match[1]) if match else None


def candidates(dist: Path) -> list[dict]:
    if not dist.exists(): return []
    require(not is_link(dist),"linked distribution root rejected")
    result=[]
    for child in dist.iterdir():
        version=sequence(child.name)
        if version is None or not child.is_dir() or is_link(child): continue
        marker=child/"package.json"
        if not marker.is_file() or is_link(marker): continue
        try: metadata=json.loads(marker.read_text(encoding="utf-8"))
        except (ValueError,OSError): continue
        if metadata.get("format") not in FORMATS or metadata.get("status")!="awaiting-user-runtime-test": continue
        if not isinstance(metadata.get("files"),dict) or "game/secondsight.EXE" not in metadata["files"]: continue
        if metadata["format"].endswith("v2"):
            if metadata.get("version")!=version or metadata.get("package_id")!=child.name: continue
        result.append(dict(path=str(child.resolve()),name=child.name,version=version,
                           manifest_sha256=hashlib.sha256(marker.read_bytes()).hexdigest()))
    require(len({r['version'] for r in result})==len(result),"ambiguous duplicate package sequence")
    return sorted(result,key=lambda r:r["version"],reverse=True)


def plan_retention(dist: Path,new_package: Path) -> dict:
    require(not is_link(dist) and not is_link(new_package),"linked retention path rejected")
    dist,new_package=dist.resolve(),new_package.resolve()
    require(new_package.parent==dist,"new package must be a direct child of dist")
    entries=candidates(dist)
    require(entries and entries[0]["path"]==str(new_package),"newly verified package must have newest sequence")
    keep,remove=entries[:KEEP],entries[KEEP:]
    for row in remove: assert_plain_tree(Path(row["path"]))
    return dict(format="second-sight-retention-v1",root=str(dist),keep=keep,remove=remove,limit=KEEP)


def apply_retention(root: Path,new_package: Path,evidence: Path) -> dict:
    plan=plan_retention(root/"dist",new_package)
    evidence.mkdir(parents=True,exist_ok=True)
    path=evidence/"retention-plan.json"
    path.write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
    # Preserve saves, settings and diagnostic logs before the checked pruner
    # removes a complete old package. Keep these small, hashed and outside dist.
    preserve_user_files(plan,evidence/"preserved-user-files")
    subprocess.run(["powershell","-NoProfile","-ExecutionPolicy","Bypass","-File",
                    str(root/"tools/prune_test_packages.ps1"),"-Plan",str(path)],check=True)
    remaining=candidates(root/"dist")
    require([x["name"] for x in remaining]==[x["name"] for x in plan["keep"]],"retention result differs from checked plan")
    print(f"RETENTION PASS: kept={len(remaining)}; removed={len(plan['remove'])}; limit={KEEP}",flush=True)
    return plan


def preserve_user_files(plan: dict, destination: Path) -> dict:
    records={}
    for row in plan["remove"]:
        source=Path(row["path"]).resolve()
        require(source.parent==Path(plan["root"]).resolve(),"backup source escapes dist")
        require(source.name==row["name"],"backup source name differs")
        assert_plain_tree(source)
        require(not destination.resolve().is_relative_to(source),"backup inside deletion target")
        for file in source.rglob("*"):
            if not file.is_file(): continue
            relative=file.relative_to(source)
            if "profiles" not in relative.parts and file.suffix.lower() not in {".cfg",".ini",".log"}: continue
            target=destination/row["name"]/relative
            digest=hashlib.sha256(file.read_bytes()).hexdigest()
            if target.exists():
                require(target.is_file() and not is_link(target) and hashlib.sha256(target.read_bytes()).hexdigest()==digest,
                        "existing user backup differs")
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                assert_plain_tree(destination)
                shutil.copy2(file,target)
            require(hashlib.sha256(target.read_bytes()).hexdigest()==digest,"user backup hash mismatch")
            records[f"{row['name']}/{relative.as_posix()}"]=digest
    if records:
        (destination/"manifest.json").write_text(json.dumps(records,indent=2)+"\n",encoding="utf-8")
        require(json.loads((destination/"manifest.json").read_text(encoding="utf-8"))==records,"user backup manifest mismatch")
    return records
