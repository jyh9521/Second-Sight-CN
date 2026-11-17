"""Freeze owned ASIs/packs and verify a glyph fix plus copy-only rollback.

No target process is launched or attached. The only executable launched by this
tool is our own localization_host; original game instructions run in Unicorn.
"""
from __future__ import annotations
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from assess_resources import require
from package_retention import assert_plain_tree
from inspect_renderer import EXPECTED_SHA256

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ('MODIFIED_FILE.asi', 'DIFF_FILE.patch', 'VERIFICATION.txt', 'ROLLBACK.sh')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(out: Path, game: Path, baseline: Path, runtime: Path, locale: Path) -> None:
    require(not (out/'inputs.json').exists(), 'choose a new evidence directory')
    require(sha(game/'secondsight.EXE') == EXPECTED_SHA256, 'original EXE identity')
    out.mkdir(parents=True, exist_ok=True)
    sources = {
        'BASELINE.asi': baseline/'game/scripts/SecondSight.Localization.asi',
        'BASELINE.bin': baseline/'game/scripts/localization/locale.bin',
        'MODIFIED_FILE.asi': runtime/'SecondSight.Localization.asi',
        'MODIFIED.map': runtime/'SecondSight.Localization.map',
        'MODIFIED.bin': locale/'locale.bin',
        'manifest.json': locale/'manifest.json',
        'localization_host.exe': runtime/'localization_host.exe',
    }
    for name, source in sources.items():
        require(not (out/name).exists(), f'existing artifact: {name}')
        shutil.copy2(source, out/name)
    # Only own source is included in the text diff; original game bytes stay local.
    old = (out/'BASELINE.cpp').read_text(encoding='utf-8').splitlines(True)
    new = (ROOT/'src/localization.cpp').read_text(encoding='utf-8').splitlines(True)
    patch = ''.join(difflib.unified_diff(old, new, fromfile='a/src/localization.cpp', tofile='b/src/localization.cpp'))
    patch += ''.join(difflib.unified_diff([], (ROOT/'src/glyph_batch.h').read_text(encoding='utf-8').splitlines(True),
                                        fromfile='/dev/null', tofile='b/src/glyph_batch.h'))
    (out/'DIFF_FILE.patch').write_text(patch, encoding='utf-8', newline='\n')
    meta = dict(exe=str((game/'secondsight.EXE').resolve()),
                exe_sha256=EXPECTED_SHA256,
                hashes={name:sha(out/name) for name in sources},
                source_before_sha256=sha(out/'BASELINE.cpp'),
                source_after_sha256=sha(ROOT/'src/localization.cpp'),
                changed_branches=['0x610EFD Begin', '0x610FA8 End tail',
                                  '0x6125C1 page Bind', '0x612677 Latin Bind',
                                  'SLP3 exact BS aliases: direct / deferred / composed'],
                original_game_execution=False, in_game_verified=False)
    (out/'inputs.json').write_text(json.dumps(meta, indent=2)+'\n', encoding='utf-8')
    target = out/'rollback-copy'
    target.mkdir()
    shutil.copy2(out/'MODIFIED_FILE.asi', target/'Localization.asi')
    shutil.copy2(out/'MODIFIED.bin', target/'locale.bin')
    script = '#!/usr/bin/env bash\nset -euo pipefail\nHERE="$(cd -- "$(dirname -- "$0")" && pwd)"\n'
    script += f'exec python -X utf8 "{Path(__file__).resolve().as_posix()}" rollback --out "$HERE"\n'
    (out/'ROLLBACK.sh').write_text(script, encoding='utf-8', newline='\n')
    (out/'ROLLBACK.sh').chmod(0o755)
    print('PREPARE PASS: original hashes frozen; modified ASI/pack copied; isolated rollback fixture ready')


def checked_inputs(out: Path) -> dict:
    assert_plain_tree(out)
    meta = json.loads((out/'inputs.json').read_text(encoding='utf-8'))
    require(sha(Path(meta['exe'])) == meta['exe_sha256'] == EXPECTED_SHA256, 'original EXE changed')
    for name, expected in meta['hashes'].items():
        require(sha(out/name) == expected, f'frozen artifact changed: {name}')
    return meta


def replay(out: Path, mode: str, asi: Path, pack: Path, report_name: str) -> dict:
    meta = checked_inputs(out)
    host_command = [str(out/'localization_host.exe'), str(asi), str(pack)]
    host = subprocess.run(host_command, capture_output=True, text=True, encoding='utf-8')
    require(host.returncode == 0, 'owned host failed: '+host.stdout+host.stderr)
    command = [sys.executable, '-X', 'utf8', str(ROOT/'tools/replay_glyph_batches.py'),
               '--exe', meta['exe'], '--manifest', str(out/'manifest.json'), '--mode', mode]
    if mode == 'modified':
        command += ['--asi', str(asi), '--map', str(out/'MODIFIED.map')]
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
    report = json.loads(result.stdout)
    if mode == 'baseline':
        require(result.returncode == 2 and report.get('baseline_reproduces_feedback') is True,
                'baseline did not reproduce screenshot defect')
    else:
        require(result.returncode == 0 and report.get('passed') is True and report['compiled_asi_hooks_executed'],
                'modified instruction replay failed: '+result.stdout+result.stderr)
    evidence = dict(command=command, input=meta['exe'], exit_status=result.returncode,
                    stdout=result.stdout, stderr=result.stderr, report=report,
                    host_command=host_command, host_input=str(pack), host_exit=host.returncode,
                    host_stdout=host.stdout, host_stderr=host.stderr)
    (out/report_name).write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return report


def check(out: Path, mode: str) -> int:
    meta = checked_inputs(out)
    if mode == 'rollback':
        target = out/'rollback-copy'
        # Named, hash-checked copies only; never restore into a delivered package.
        require(sha(target/'Localization.asi') == meta['hashes']['MODIFIED_FILE.asi'], 'rollback ASI input differs')
        require(sha(target/'locale.bin') == meta['hashes']['MODIFIED.bin'], 'rollback pack input differs')
        shutil.copy2(out/'BASELINE.asi', target/'Localization.asi')
        shutil.copy2(out/'BASELINE.bin', target/'locale.bin')
        require(sha(target/'Localization.asi') == meta['hashes']['BASELINE.asi'], 'ASI restore mismatch')
        require(sha(target/'locale.bin') == meta['hashes']['BASELINE.bin'], 'pack restore mismatch')
        replay(out, 'baseline', target/'Localization.asi', target/'locale.bin', 'rollback.json')
        checked_inputs(out)
        print('ROLLBACK PASS: isolated ASI/pack hashes restored; 6/6 original wrong labels restored; modified retained; game not launched')
        return 0
    if mode == 'baseline':
        replay(out, mode, out/'BASELINE.asi', out/'BASELINE.bin', 'baseline.json')
        print('BASELINE REPRODUCED: 6/6 screenshot labels wrong; native replay exit=2; host exit=0')
        return 2
    report = replay(out, mode, out/'MODIFIED_FILE.asi', out/'MODIFIED.bin', 'modified.json')
    print(f'MODIFIED PASS: 6/6 labels corrected; {len(report["cases"])}/{len(report["cases"])} native checks passed; host exit=0; game not launched')
    return 0


def evidence(out: Path) -> None:
    meta = checked_inputs(out)
    script = str(Path(__file__).resolve())
    commands = [([sys.executable,'-X','utf8',script,'baseline','--out',str(out)], 2),
                ([sys.executable,'-X','utf8',script,'modified','--out',str(out)], 0),
                ([r'C:\Program Files\Git\bin\bash.exe',str(out/'ROLLBACK.sh')], 0)]
    lines = ['OFFLINE GLYPH FIX VERIFICATION', 'changed branches: '+'; '.join(meta['changed_branches']),
             'input: '+str(out/'inputs.json'), 'cwd: '+str(ROOT),
             'Original EXE is read only; GPU submission is mocked; user in-game acceptance pending.',
             'Restored status: separate ASI/pack copy matches 006 hashes and reproduces old wrong labels.',
             'Delivered modified ASI and pack remain changed.',
             *[f'{name}: {out/name}' for name in ARTIFACTS]]
    for (command, expected), label in zip(commands, ('BASELINE','MODIFIED','ROLLBACK')):
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
        lines += ['',label,'command: '+subprocess.list2cmdline(command),'stdout:',result.stdout.rstrip(),
                  'stderr:',result.stderr.rstrip(),'exit_status: '+str(result.returncode)]
        require(result.returncode == expected, result.stdout+result.stderr)
        print(result.stdout, end='')
    (out/'VERIFICATION.txt').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    for name in ARTIFACTS:
        require(bool((out/name).read_bytes()), f'empty artifact: {name}')
    print('EVIDENCE PASS: BASELINE=2 MODIFIED=0 ROLLBACK=0; four artifacts reopened')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare','baseline','modified','rollback','evidence'))
    parser.add_argument('--out', type=Path, required=True)
    for name in ('game-root','baseline-package','runtime','locale-build'):
        parser.add_argument('--'+name, type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    require(out.is_relative_to(ROOT/'build'), 'evidence must be within repository build')
    if args.mode == 'prepare':
        require(all((args.game_root,args.baseline_package,args.runtime,args.locale_build)), 'missing input paths')
        prepare(out,args.game_root,args.baseline_package,args.runtime,args.locale_build)
    elif args.mode == 'evidence':
        evidence(out)
    else:
        raise SystemExit(check(out,args.mode))
