"""Read-only audit of pinned FusionFix source write sites and locale code spans."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from assess_resources import require
from startup_compat import mapped_game,transform,contracts

ROOT=Path(__file__).resolve().parents[1]
PIN='7bce79ffaeee61f95db59a68b35a150cd8644223'


def inspect(exe: Path, checkout: Path) -> dict:
    profile=json.loads((ROOT/'assets/full-text-contracts.json').read_text(encoding='utf-8'))
    sources={}
    for name in ['dllmain.cpp','Camera.ixx','ComVars.ixx','Cutscenes.ixx','Hud.ixx','Misc.ixx','Movies.ixx','Renderer.ixx','Resolution.ixx','ResolutionHooks.cpp','Window.ixx']:
        sources[name]=subprocess.check_output(['git','-C',str(checkout),'show',f'{PIN}:source/SecondSight.FusionFix/{name}'])
    rows=contracts(transform(mapped_game(exe)))
    spans=[(0x611c70,6),(0x5d0643,5),(0x5d06fb,5),
           (0x610efd,5),(0x610fa8,5),(0x6125c1,5),(0x612677,5)]
    spans += [(int(r['va'],16),len(bytes.fromhex(r['before']))) for r in profile['atlas']['patches']]
    literal=json.loads((ROOT/'assets/exe-text-contracts.json').read_text(encoding='utf-8'))
    spans += [(int(r['patch_va'],16),len(bytes.fromhex(r['expected']))) for r in literal['records']]
    for row in rows:
        require(row['pattern'] in sources[row['source']].decode(),'pattern not in pinned source')
        require(row['passed'],'pattern did not match uniquely')
        start=int(row['expected_address'],16)
        require(all(not(start<a+n and a<start+96) for a,n in spans),'overlap with FusionFix pattern envelope')
    return dict(commit=PIN,source_hashes={n:hashlib.sha256(v).hexdigest() for n,v in sources.items()},
                new_localization_spans=[dict(address=hex(a),size=n) for a,n in spans],
                pattern_contract='assets/fusionfix-startup-contracts.json',matched_patterns=len(rows),
                pattern_code_envelope=96,startup_view='after four existing compatibility contracts; original disk unchanged',
                result=f'PASS: {len(rows)} pinned game-pattern envelopes are disjoint from {len(spans)} new code spans',
                scope='static write-site audit, not runtime module-order or device acceptance',
                nearest_text_hooks=['0x612BC0','0x613330'],game_executed=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--exe',type=Path,required=True)
    p.add_argument('--fusionfix-source',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();before=hashlib.sha256(a.exe.read_bytes()).hexdigest()
    report=inspect(a.exe,a.fusionfix_source)
    require(hashlib.sha256(a.exe.read_bytes()).hexdigest()==before,'original EXE changed')
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    require(json.loads(a.out.read_text(encoding='utf-8'))==report,'report reopen mismatch')
    print(report['result'])
