"""Verify all BS translations on an offline copy and test byte-exact rollback.

The rebuilt BS is evidence only. The installed patch still uses the runtime
pack and its direct/deferred consumer contracts, never this full resource.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from assess_resources import Pak, StringTable, require
from build_locale import ROOT, BS_SHA, EXE_SHA, digest, encode, decode


def prepare(game: Path, locale_build: Path, out: Path) -> None:
    require(not out.exists(), 'evidence directory already exists')
    archive = game / 'pak/arcade/l_103.pak'
    archive_bytes = archive.read_bytes()
    baseline = Pak(archive_bytes).member('data/strsspxe.bs')
    require(digest(baseline) == BS_SHA, 'unsupported BS input')
    manifest_bytes = (locale_build / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    require(manifest['complete_inventory']['all_ids_accounted'], 'complete inventory required')
    require(digest((locale_build / 'locale.bin').read_bytes()) == manifest['pack_sha256'], 'pack identity mismatch')
    table = StringTable(baseline)
    targets = {int(k): v for k, v in manifest['targets']['bs'].items()}
    rebuilt = table.replace_many({i: encode(t, manifest['glyphs']) for i, t in targets.items()})
    modified = StringTable(rebuilt)
    out.mkdir(parents=True)
    (out / 'BASELINE.bs').write_bytes(baseline)
    (out / 'MODIFIED_FILE.bs').write_bytes(rebuilt)
    (out / 'locale-manifest.json').write_bytes(manifest_bytes)
    metadata = dict(source_archive=str(archive.resolve()), source_archive_sha256=digest(archive_bytes),
                    source_executable=str((game / 'secondsight.EXE').resolve()), source_executable_sha256=EXE_SHA,
                    baseline_sha256=digest(baseline), modified_sha256=digest(rebuilt),
                    fields=[dict(id=i, field=i*4, old_pointer=table.offsets[i], new_pointer=modified.offsets[i]) for i in sorted(targets)],
                    status='offline full BS copy; not installed; no game execution',
                    runtime_branches=['BS/PDA pointer substitution with exact source checks',
                                      'six 512x512 Source Han atlas pages; 6142 allocatable glyphs',
                                      'guarded page/grid immediates at 0x612595..0x6125FC',
                                      'owned token-aware wrapping at 0x611C70'])
    (out / 'DIFF_FILE.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8', newline='\n')
    script = '#!/usr/bin/env bash\nset -euo pipefail\nHERE="$(cd -- "$(dirname -- "$0")" && pwd)"\n'
    script += 'if [ "$#" -ne 1 ]; then echo "Usage: ROLLBACK.sh TARGET_COPY" >&2; exit 2; fi\n'
    script += f'exec python -X utf8 "{Path(__file__).resolve().as_posix()}" restore --out "$HERE" --target "$1"\n'
    (out / 'ROLLBACK.sh').write_text(script, encoding='utf-8', newline='\n')
    (out / 'ROLLBACK.sh').chmod(0o755)
    shutil.copy2(out / 'MODIFIED_FILE.bs', out / 'ROLLBACK_TEST.bs')
    print(f'PREPARE PASS: BS fields={len(targets)}; original preserved; modified copy retained')


def check(stage: str, out: Path, target: Path | None = None) -> None:
    meta = json.loads((out / 'DIFF_FILE.json').read_text(encoding='utf-8'))
    manifest = json.loads((out / 'locale-manifest.json').read_text(encoding='utf-8'))
    baseline = (out / 'BASELINE.bs').read_bytes()
    modified = (out / 'MODIFIED_FILE.bs').read_bytes()
    require(digest(baseline) == meta['baseline_sha256'] == BS_SHA, 'baseline identity changed')
    require(digest(modified) == meta['modified_sha256'], 'modified identity changed')
    require(digest(Path(meta['source_archive']).read_bytes()) == meta['source_archive_sha256'], 'original archive changed')
    require(digest(Path(meta['source_executable']).read_bytes()) == EXE_SHA, 'original executable changed')
    a, b = StringTable(baseline), StringTable(modified)
    if stage == 'baseline':
        require(a.replace_many({}) == baseline and a.strings[850] == b'New Game', 'baseline roundtrip mismatch')
        print('BASELINE PASS: BS=6526 IDs; ID850=New Game; roundtrip=identical; original EXE/PAK unchanged')
    elif stage == 'modified':
        targets = {int(k): v for k, v in manifest['targets']['bs'].items()}
        require(len(a.strings) == len(b.strings), 'table count changed')
        require({i for i, pair in enumerate(zip(a.strings, b.strings)) if pair[0] != pair[1]} == set(targets), 'unexpected changed IDs')
        for identifier, value in targets.items():
            require(decode(b.strings[identifier], manifest['glyphs']) == value, f'BS {identifier}: target decoding mismatch')
        allowed = {i*4+j for i in targets for j in range(4)}
        require(all(value == modified[i] for i, value in enumerate(baseline) if i not in allowed), 'unrelated baseline bytes changed')
        print(f'MODIFIED PASS: BS fields={len(targets)}; all targets decoded; unselected IDs={len(a.strings)-len(targets)} unchanged; runtime=PENDING')
    elif stage == 'restore':
        require(target is not None and target.resolve() == (out / 'ROLLBACK_TEST.bs').resolve(), 'only designated rollback copy accepted')
        require(target.read_bytes() == modified, 'rollback input differs from modified copy')
        target.write_bytes(baseline)
        require(target.read_bytes() == baseline, 'restore mismatch')
        print('RESTORE PASS: isolated ROLLBACK_TEST.bs restored byte-for-byte; modified artifact retained')
    elif stage == 'rollback':
        require((out / 'ROLLBACK_TEST.bs').read_bytes() == baseline, 'rollback differs from original')
        print('ROLLBACK PASS: original BS bytes/text restored; MODIFIED_FILE.bs retained; original EXE/PAK unchanged')


def evidence(out: Path) -> None:
    local = out.relative_to(ROOT).as_posix()
    commands = [[sys.executable, '-X', 'utf8', 'tools/verify_full_catalog.py', stage, '--out', local] for stage in ('baseline', 'modified')]
    commands += [[r'C:\Program Files\Git\bin\bash.exe', f'{local}/ROLLBACK.sh', f'{local}/ROLLBACK_TEST.bs'],
                 [sys.executable, '-X', 'utf8', 'tools/verify_full_catalog.py', 'rollback', '--out', local]]
    meta = json.loads((out / 'DIFF_FILE.json').read_text(encoding='utf-8'))
    lines = ['Full BS offline verification', f'cwd={ROOT}', f'changed fields={len(meta["fields"])} BS pointer fields; each field listed in DIFF_FILE.json',
             'input=original pinned BS; modified=frozen locale targets; rollback=separate modified copy',
             'runtime branches=' + '; '.join(meta['runtime_branches']), 'game execution=NO; runtime acceptance=PENDING']
    for name in ('MODIFIED_FILE.bs', 'DIFF_FILE.json', 'VERIFICATION.txt', 'ROLLBACK.sh'):
        lines.append(f'{name}={out/name}')
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
        lines.extend(['', 'COMMAND: ' + subprocess.list2cmdline(command), f'EXIT: {result.returncode}', 'STDOUT:', result.stdout.rstrip(), 'STDERR:', result.stderr.rstrip()])
        require(result.returncode == 0, result.stdout + result.stderr)
    (out / 'VERIFICATION.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    for name in ('MODIFIED_FILE.bs', 'DIFF_FILE.json', 'VERIFICATION.txt', 'ROLLBACK.sh'):
        require(bool((out/name).read_bytes()), f'artifact reopen failed: {name}')
    print('EVIDENCE PASS: baseline, modified, rollback exit=0; four artifacts reopened; game NOT launched')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['prepare', 'baseline', 'modified', 'restore', 'rollback', 'evidence'])
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--game-root', type=Path)
    parser.add_argument('--locale-build', type=Path)
    parser.add_argument('--target', type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    if args.stage == 'prepare': prepare(args.game_root, args.locale_build, out)
    elif args.stage == 'evidence': evidence(out)
    else: check(args.stage, out, args.target)
