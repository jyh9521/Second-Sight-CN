"""Freeze a subtitle candidate and verify native layout plus copy-only rollback.

The game is never launched or attached. Only our owned host executes as a
Windows process; hash-bound game instructions are replayed inside Unicorn.
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

ROOT=Path(__file__).resolve().parents[1]
ARTIFACTS=('MODIFIED_FILE.asi','DIFF_FILE.patch','VERIFICATION.txt','ROLLBACK.sh')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(out: Path, game: Path, baseline: Path, runtime: Path) -> None:
    require(not (out/'inputs.json').exists(),'choose a fresh evidence directory')
    require(sha(game/'secondsight.EXE')==EXPECTED_SHA256,'original EXE identity')
    out.mkdir(parents=True,exist_ok=True)
    assert_plain_tree(out)
    sources={
        'BASELINE.asi':baseline/'game/scripts/SecondSight.Localization.asi',
        'locale.bin':baseline/'game/scripts/localization/locale.bin',
        'MODIFIED_FILE.asi':runtime/'SecondSight.Localization.asi',
        'MODIFIED.map':runtime/'SecondSight.Localization.map',
        'localization_host.exe':runtime/'localization_host.exe',
    }
    for name,source in sources.items():
        require(not (out/name).exists(),f'existing artifact: {name}')
        shutil.copy2(source,out/name)
    old=(out/'BASELINE.cpp').read_text(encoding='utf-8').splitlines(True)
    new=(ROOT/'src/localization.cpp').read_text(encoding='utf-8').splitlines(True)
    diff=''.join(difflib.unified_diff(old,new,fromfile='a/src/localization.cpp',tofile='b/src/localization.cpp'))
    diff+=''.join(difflib.unified_diff([], (ROOT/'src/subtitle_layout.h').read_text(encoding='utf-8').splitlines(True),
                                     fromfile='/dev/null',tofile='b/src/subtitle_layout.h'))
    (out/'DIFF_FILE.patch').write_text(diff,encoding='utf-8',newline='\n')
    meta=dict(exe=str((game/'secondsight.EXE').resolve()),exe_sha256=EXPECTED_SHA256,
              hashes={name:sha(out/name) for name in sources},
              baseline_package=str(baseline.resolve()),source_before_sha256=sha(out/'BASELINE.cpp'),
              source_after_sha256=sha(ROOT/'src/localization.cpp'),
              changed_branches=['0x543031 call beginCutscene','0x5431E8 jmp endCutsceneHook'],
              changed_field='private Style.x/Style.y *= RenderHeight/480; original selection restored',
              original_game_execution=False,in_game_verified=False,package_created=False)
    (out/'inputs.json').write_text(json.dumps(meta,indent=2)+'\n',encoding='utf-8')
    target=out/'rollback-copy';target.mkdir()
    shutil.copy2(out/'MODIFIED_FILE.asi',target/'Localization.asi')
    script='#!/usr/bin/env bash\nset -euo pipefail\nHERE="$(cd -- "$(dirname -- "$0")" && pwd)"\n'
    script+=f'exec python -X utf8 "{Path(__file__).resolve().as_posix()}" rollback --out "$HERE"\n'
    (out/'ROLLBACK.sh').write_text(script,encoding='utf-8',newline='\n')
    (out/'ROLLBACK.sh').chmod(0o755)
    print('PREPARE PASS: original hashes frozen; candidate copied; isolated rollback ready')


def checked_inputs(out: Path) -> dict:
    assert_plain_tree(out)
    meta=json.loads((out/'inputs.json').read_text(encoding='utf-8'))
    require(sha(Path(meta['exe']))==meta['exe_sha256']==EXPECTED_SHA256,'original EXE changed')
    for name,expected in meta['hashes'].items():
        require(sha(out/name)==expected,f'frozen artifact changed: {name}')
    return meta


def run_record(command: list[str]) -> dict:
    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    return dict(command=command,input_cwd=str(ROOT),stdout=result.stdout,stderr=result.stderr,exit_status=result.returncode)


def check(out: Path,mode: str) -> int:
    meta=checked_inputs(out)
    asi=out/('MODIFIED_FILE.asi' if mode=='modified' else 'BASELINE.asi')
    if mode=='rollback':
        asi=out/'rollback-copy/Localization.asi'
        require(sha(asi)==meta['hashes']['MODIFIED_FILE.asi'],'rollback input differs')
        shutil.copy2(out/'BASELINE.asi',asi)
        require(sha(asi)==meta['hashes']['BASELINE.asi'],'rollback ASI restore mismatch')
    host=run_record([str(out/'localization_host.exe'),str(asi),str(out/'locale.bin')])
    require(host['exit_status']==0,'owned host failed: '+host['stdout']+host['stderr'])
    command=[sys.executable,'-X','utf8',str(ROOT/'tools/replay_subtitle_layout.py'),
             '--exe',meta['exe'],'--out',str(out/f'native-{mode}.json')]
    command+=['--library',str(out/'MODIFIED_FILE.asi'),'--map',str(out/'MODIFIED.map')]
    if mode=='baseline':command+=['--baseline-with-library']
    if mode=='rollback':command+=['--rollback']
    replay=run_record(command)
    require(replay['exit_status']==(0 if mode=='modified' else 1),'unexpected native replay result: '+replay['stdout']+replay['stderr'])
    report=json.loads((out/f'native-{mode}.json').read_text(encoding='utf-8'))
    require(report['passed']==(mode=='modified'),'native result inconsistent')
    if mode=='rollback':
        baseline=json.loads((out/'native-baseline.json').read_text(encoding='utf-8'))
        require(report['cases']==baseline['cases'],'restored native behavior differs from baseline')
    evidence=dict(host=host,replay=replay,mode=mode,asi_sha256=sha(asi),locale_sha256=sha(out/'locale.bin'),
                  baseline_note='007 ASI identity/host restored separately; native baseline executes the unchanged 007 wrap code in the new ASI without scale hooks; rollback restores only two layout sites, not a live process')
    (out/f'{mode}.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    checked_inputs(out)
    if mode=='baseline':
        print('BASELINE REPRODUCED: native layout exit=1; host exit=0; fixed-pixel subtitle defect')
        return 1
    if mode=='modified':
        print(f'MODIFIED PASS: {len(report["cases"])}/{len(report["cases"])} native layout checks; host exit=0; game not launched')
        return 0
    print('ROLLBACK PASS: isolated ASI restored to 007; native cases equal baseline; modified retained; game not launched')
    return 0


def evidence(out: Path) -> None:
    meta=checked_inputs(out)
    commands=[([sys.executable,'-X','utf8',str(Path(__file__).resolve()),mode,'--out',str(out)],status)
              for mode,status in [('baseline',1),('modified',0)]]
    commands.append(([r'C:\Program Files\Git\bin\bash.exe',str(out/'ROLLBACK.sh')],0))
    lines=['OFFLINE SUBTITLE FIX VERIFICATION','cwd: '+str(ROOT),
           'changed branches: '+'; '.join(meta['changed_branches']),'changed field: '+meta['changed_field'],
           'input: '+str(out/'inputs.json'),
           'Original EXE read only. Layout/GPU boundaries documented in docs/research/SUBTITLE_008.md.',
           'Restored status: isolated ASI has 007 identity; native layout cases match the fixed-pixel baseline.',
           'Candidate remains changed. No game launch, package mutation or runtime/pixel acceptance.',
           *[f'{name}: {out/name}' for name in ARTIFACTS]]
    for (command,expected),label in zip(commands,('BASELINE','MODIFIED','ROLLBACK')):
        result=run_record(command)
        lines+=['',label,'command: '+subprocess.list2cmdline(command),'stdout:',result['stdout'].rstrip(),
                'stderr:',result['stderr'].rstrip(),'exit_status: '+str(result['exit_status'])]
        require(result['exit_status']==expected,result['stdout']+result['stderr'])
        print(result['stdout'],end='')
        detail=json.loads((out/f'{label.lower()}.json').read_text(encoding='utf-8'))
        for key in ('host','replay'):
            row=detail[key]
            lines+=[key+' command: '+subprocess.list2cmdline(row['command']),key+' input: '+str(out/'locale.bin') if key=='host' else 'replay input: '+meta['exe'],
                    key+' stdout:',row['stdout'].rstrip(),key+' stderr:',row['stderr'].rstrip(),key+' exit_status: '+str(row['exit_status'])]
    (out/'VERIFICATION.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    for name in ARTIFACTS:require(bool((out/name).read_bytes()),f'empty artifact: {name}')
    print('EVIDENCE PASS: BASELINE=1 MODIFIED=0 ROLLBACK=0; four artifacts reopened')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','baseline','modified','rollback','evidence'))
    parser.add_argument('--out',type=Path,required=True)
    for name in ('game-root','baseline-package','runtime'):parser.add_argument('--'+name,type=Path)
    args=parser.parse_args();out=args.out.resolve()
    require(out.is_relative_to(ROOT/'build'),'evidence must be within repository build')
    if args.mode=='prepare':
        require(all((args.game_root,args.baseline_package,args.runtime)),'missing input paths')
        prepare(out,args.game_root,args.baseline_package,args.runtime)
    elif args.mode=='evidence':evidence(out)
    else:raise SystemExit(check(out,args.mode))
