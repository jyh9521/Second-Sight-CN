"""Freeze and replay the added speech captions and cutscene scale; no game launch."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys

from assess_resources import require
from inspect_renderer import EXPECTED_SHA256
from package_retention import assert_plain_tree

ROOT=Path(__file__).resolve().parents[1]
ARTIFACTS=('MODIFIED_FILE.asi','DIFF_FILE.patch','VERIFICATION.txt','ROLLBACK.sh')

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def run(command):
    p=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    return dict(command=command,cwd=str(ROOT),stdout=p.stdout,stderr=p.stderr,exit_status=p.returncode)

def prepare(out,game,baseline,runtime,locale):
    require(not out.exists(),'choose a new evidence directory')
    require(sha(game/'secondsight.EXE')==EXPECTED_SHA256,'EXE identity mismatch')
    out.mkdir(parents=True)
    sources={'BASELINE.asi':baseline/'game/scripts/SecondSight.Localization.asi',
             'BASELINE_LOCALE.bin':baseline/'game/scripts/localization/locale.bin',
             'MODIFIED_FILE.asi':runtime/'SecondSight.Localization.asi',
             'MODIFIED.map':runtime/'SecondSight.Localization.map',
             'locale.bin':locale/'locale.bin','localization_host.exe':runtime/'localization_host.exe'}
    for name,source in sources.items(): shutil.copy2(source,out/name)
    # The baseline is the released local 007 module, not the earlier scale-only work.
    paths=['src/localization.cpp','src/subtitle_layout.h','src/gameplay_captions.h']
    diff=subprocess.check_output(['git','diff','10d4dfc7cc30f9a3f251fe1a6cc16a437c73b185','--',*paths],cwd=ROOT)
    import difflib
    # New untracked files are not returned by git diff before staging.
    tracked=subprocess.check_output(['git','ls-files',*paths],cwd=ROOT,text=True).splitlines()
    for file in paths:
        if file not in tracked:
            diff+=''.join(difflib.unified_diff([], (ROOT/file).read_text(encoding='utf-8').splitlines(True),
                         fromfile='/dev/null',tofile='b/'+file)).encode('utf-8')
    (out/'DIFF_FILE.patch').write_bytes(diff)
    meta=dict(exe=str((game/'secondsight.EXE').resolve()),exe_sha256=EXPECTED_SHA256,
              baseline_package=str(baseline.resolve()),hashes={n:sha(out/n) for n in sources},
              changed_branches=['0x456610 speech event observer','0x63D78A gameplay draw call','0x63D494 HUD reset call',
                                '0x543031 cutscene begin','0x5431E8 cutscene restore'],
              changed_fields='copied owner/BS/audio/priority state; private Style.x/Style.y *= RenderHeight/480',
              game_launched=False,in_game_verified=False)
    (out/'inputs.json').write_text(json.dumps(meta,indent=2)+'\n',encoding='utf-8')
    target=out/'rollback-copy';target.mkdir()
    shutil.copy2(out/'MODIFIED_FILE.asi',target/'Localization.asi')
    shutil.copy2(out/'locale.bin',target/'locale.bin')
    script='#!/usr/bin/env bash\nset -euo pipefail\nHERE="$(cd -- "$(dirname -- "$0")" && pwd)"\n'
    script+=f'exec python -X utf8 "{Path(__file__).resolve().as_posix()}" rollback --out "$HERE"\n'
    (out/'ROLLBACK.sh').write_text(script,encoding='utf-8',newline='\n')
    (out/'ROLLBACK.sh').chmod(0o755)
    print('PREPARE PASS: original and candidate hashes frozen; isolated rollback ready')

def inputs(out):
    assert_plain_tree(out)
    meta=json.loads((out/'inputs.json').read_text(encoding='utf-8'))
    require(sha(Path(meta['exe']))==meta['exe_sha256']==EXPECTED_SHA256,'EXE changed')
    for name,digest in meta['hashes'].items(): require(sha(out/name)==digest,'frozen input changed: '+name)
    return meta

def check(out,mode):
    meta=inputs(out)
    if mode=='rollback':
        require(sha(out/'rollback-copy/Localization.asi')==meta['hashes']['MODIFIED_FILE.asi'],'rollback ASI input changed')
        require(sha(out/'rollback-copy/locale.bin')==meta['hashes']['locale.bin'],'rollback locale input changed')
        shutil.copy2(out/'BASELINE.asi',out/'rollback-copy/Localization.asi')
        shutil.copy2(out/'BASELINE_LOCALE.bin',out/'rollback-copy/locale.bin')
        require(sha(out/'rollback-copy/Localization.asi')==meta['hashes']['BASELINE.asi'],'restored ASI differs')
        require(sha(out/'rollback-copy/locale.bin')==meta['hashes']['BASELINE_LOCALE.bin'],'restored locale differs')
        asi,locale=out/'rollback-copy/Localization.asi',out/'rollback-copy/locale.bin'
    elif mode=='baseline': asi,locale=out/'BASELINE.asi',out/'BASELINE_LOCALE.bin'
    else: asi,locale=out/'MODIFIED_FILE.asi',out/'locale.bin'
    details={'host':run([str(out/'localization_host.exe'),str(asi),str(locale)])}
    require(details['host']['exit_status']==0,'owned host failed: '+str(details['host']))
    counts={}
    for kind,tool in [('gameplay','replay_gameplay_caption_events.py'),('cutscene','replay_subtitle_layout.py')]:
        command=[sys.executable,'-X','utf8',str(ROOT/'tools'/tool),'--exe',meta['exe'],
                 '--library',str(out/'MODIFIED_FILE.asi'),'--map',str(out/'MODIFIED.map'),
                 '--out',str(out/f'{kind}-{mode}.json')]
        if kind=='gameplay': command+=['--require-added-captions']
        if mode=='baseline': command+=['--baseline-with-library']
        if mode=='rollback': command+=['--rollback']
        details[kind]=run(command)
        require(details[kind]['exit_status']==(0 if mode=='modified' else 1),str(details[kind]))
        report=json.loads((out/f'{kind}-{mode}.json').read_text(encoding='utf-8'))
        require(report['passed']==(mode=='modified'),'unexpected replay result')
        counts[kind]=len(report['cases'])
        if mode=='rollback':
            base=json.loads((out/f'{kind}-baseline.json').read_text(encoding='utf-8'))
            require(report['cases']==base['cases'],'restored cases differ: '+kind)
    (out/f'{mode}.json').write_text(json.dumps(details,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    inputs(out)
    if mode=='baseline':
        print('BASELINE REPRODUCED: gameplay=1; cutscene=1; host=0; added captions absent and fixed pixel scale')
        return 1
    if mode=='modified':
        print(f'MODIFIED PASS: gameplay={counts["gameplay"]}/{counts["gameplay"]}; cutscene={counts["cutscene"]}/{counts["cutscene"]}; host=0; game_launched=false')
        return 0
    print('ROLLBACK PASS: isolated ASI and locale restored to 007; native cases equal baseline; modified retained; game_launched=false')
    return 0

def evidence(out):
    meta=inputs(out)
    lines=['OFFLINE GAMEPLAY CAPTION VERIFICATION','cwd: '+str(ROOT),
           'changed branches: '+'; '.join(meta['changed_branches']),'changed fields: '+meta['changed_fields'],
           'inputs: '+str(out/'inputs.json'),
           'Restored behavior/status: independent files return to 007 hashes; five native patch sites return to baseline cases.',
           'Baseline/replay uses current unchanged wrap code with caption hooks disabled; actual 007 module tested separately by owned host.',
           'Audio/locale input/GPU/OS boundaries are synthetic. No game launch or in-game acceptance.',
           *[f'{name}: {out/name}' for name in ARTIFACTS]]
    commands=[([sys.executable,'-X','utf8',str(Path(__file__).resolve()),mode,'--out',str(out)],expected)
              for mode,expected in [('baseline',1),('modified',0)]]
    commands.append(([r'C:\Program Files\Git\bin\bash.exe',str(out/'ROLLBACK.sh')],0))
    for (command,expected),label in zip(commands,['BASELINE','MODIFIED','ROLLBACK']):
        result=run(command)
        lines+=['',label,'command: '+subprocess.list2cmdline(command),'input: '+str(out/'inputs.json'),
                'stdout:',result['stdout'].rstrip(),'stderr:',result['stderr'].rstrip(),'exit_status: '+str(result['exit_status'])]
        require(result['exit_status']==expected,str(result)); print(result['stdout'],end='')
        detail=json.loads((out/f'{label.lower()}.json').read_text(encoding='utf-8'))
        for key,row in detail.items():
            lines += [key+' command: '+subprocess.list2cmdline(row['command']),key+' stdout:',row['stdout'].rstrip(),
                      key+' stderr:',row['stderr'].rstrip(),key+' exit_status: '+str(row['exit_status'])]
    (out/'VERIFICATION.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    for name in ARTIFACTS: require(bool((out/name).read_bytes()),'artifact missing: '+name)
    print('EVIDENCE PASS: BASELINE=1 MODIFIED=0 ROLLBACK=0; four artifacts reopened')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['prepare','baseline','modified','rollback','evidence'])
    p.add_argument('--out',type=Path,required=True)
    for name in ['game-root','baseline-package','runtime','locale-build']: p.add_argument('--'+name,type=Path)
    a=p.parse_args();out=a.out.resolve()
    require(out.is_relative_to(ROOT/'build'),'evidence must be within repository build')
    if a.mode=='prepare':
        require(all([a.game_root,a.baseline_package,a.runtime,a.locale_build]),'missing preparation inputs')
        prepare(out,a.game_root,a.baseline_package,a.runtime,a.locale_build)
    elif a.mode=='evidence': evidence(out)
    else: raise SystemExit(check(out,a.mode))
