"""Read-only full input inventory. This is NOT a build preflight or G0 pass."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import stat


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inventory(root: Path, platform: str, region: str, version: str, role: str) -> dict:
    root = root.absolute()
    def plain(path):
        info = path.lstat()
        if path.is_symlink() or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError('linked input requires explicit treatment: '+str(path))
    for ancestor in (root, *root.parents):
        plain(ancestor)
    files = []
    def scan(directory):
        for path in sorted(directory.iterdir()):
            plain(path)
            if path.is_dir():
                scan(path)
            elif path.is_file():
                before = path.stat()
                digest = sha256(path)
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError('input changed while hashing: '+str(path))
                files.append(dict(path=path.relative_to(root).as_posix(), bytes=after.st_size,
                                  sha256=digest, role=role))
    scan(root)
    return dict(schema=1, platform=platform, region=region, version=version,
                status='inventory_only_not_G0_acceptance', files=files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    for name in ('platform', 'region', 'version', 'role'):
        parser.add_argument('--'+name, required=True)
    args = parser.parse_args()
    if args.out.resolve().is_relative_to(args.root.resolve()):
        parser.error('output must be outside original input tree')
    report = inventory(args.root, args.platform, args.region, args.version, args.role)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f"INPUT_INVENTORY: files={len(report['files'])}; writes_to_input=0; G0=not_run")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
