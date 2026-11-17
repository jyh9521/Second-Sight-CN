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
CUTSCENES_SHA256='3538d30871c0d8b4a1d7e7054575c9b755c42f6ad5b041abd56cb07181bbfe42'
# These two patterns surround, but do not write, the subtitle SetFont call.
# Bind the narrower footprints to the whole audited pinned source, not a
# permissive overlap allowlist. All other patterns retain the 96-byte envelope.
CUTSCENE_WRITES={
    'DB 05 ? ? ? ? 6A 7F D8 0D ? ? ? ? E8 ? ? ? ? 50 A1 ? ? ? ? 50 6A 00 6A 00 E8':
        (0x542fe0, ((0,6),(10,4))),  # x86 mid hook: first complete 6-byte FILD; pointer operand
    'DB 05 ? ? ? ? 8B 35 ? ? ? ? 8B 0D ? ? ? ? D8 0D ? ? ? ? 6A 7F':
        (0x543003, ((20,4),)),       # pointer operand only; no mid hook at bottom
}


def write_envelopes(row: dict, source: bytes) -> list[tuple[int,int]]:
    start=int(row['expected_address'],16)
    if row['source']=='Cutscenes.ixx' and row['pattern'] in CUTSCENE_WRITES:
        require(hashlib.sha256(source).hexdigest()==CUTSCENES_SHA256,
                'cutscene write-footprint source identity changed; re-audit required')
        expected,offsets=CUTSCENE_WRITES[row['pattern']]
        require(start==expected,'cutscene write-footprint address changed')
        return [(start+offset,size) for offset,size in offsets]
    return [(start,96)]


def require_disjoint(writes: list[tuple[int,int]], spans: list[tuple[int,int]]) -> None:
    for start,size in writes:
        require(all(not(start<a+n and a<start+size) for a,n in spans),
                f'overlap with FusionFix write envelope at {start:#x}')


def inspect(exe: Path, checkout: Path) -> dict:
    profile=json.loads((ROOT/'assets/full-text-contracts.json').read_text(encoding='utf-8'))
    sources={}
    for name in ['dllmain.cpp','Camera.ixx','ComVars.ixx','Cutscenes.ixx','Hud.ixx','Misc.ixx','Movies.ixx','Renderer.ixx','Resolution.ixx','ResolutionHooks.cpp','Window.ixx']:
        sources[name]=subprocess.check_output(['git','-C',str(checkout),'show',f'{PIN}:source/SecondSight.FusionFix/{name}'])
    rows=contracts(transform(mapped_game(exe)))
    spans=[(0x456610,5),(0x63d78a,5),(0x63d494,5),
           (0x543031,5),(0x5431e8,6),(0x611c70,6),(0x5d0643,5),(0x5d06fb,5),
           (0x610efd,5),(0x610fa8,5),(0x6125c1,5),(0x612677,5)]
    from inspect_renderer import PATCH_SITES
    spans += [(a,len(bytes.fromhex(b))) for name,(a,b) in PATCH_SITES.items() if name.startswith('hd_atlas_')]
    spans += [(int(r['va'],16),len(bytes.fromhex(r['before']))) for r in profile['atlas']['patches']]
    literal=json.loads((ROOT/'assets/exe-text-contracts.json').read_text(encoding='utf-8'))
    spans += [(int(r['patch_va'],16),len(bytes.fromhex(r['expected']))) for r in literal['records']]
    audited=[]
    for row in rows:
        require(row['pattern'] in sources[row['source']].decode(),'pattern not in pinned source')
        require(row['passed'],'pattern did not match uniquely')
        writes=write_envelopes(row,sources[row['source']])
        require_disjoint(writes,spans)
        audited.append(dict(source=row['source'],pattern_address=row['expected_address'],
                            writes=[dict(address=hex(a),size=n) for a,n in writes],
                            method='source-bound cutscene writes' if row['pattern'] in CUTSCENE_WRITES
                            else 'conservative 96-byte pattern envelope'))
    return dict(commit=PIN,source_hashes={n:hashlib.sha256(v).hexdigest() for n,v in sources.items()},
                new_localization_spans=[dict(address=hex(a),size=n) for a,n in spans],
                pattern_contract='assets/fusionfix-startup-contracts.json',matched_patterns=len(rows),
                pattern_code_envelope=96,audited_write_envelopes=audited,
                startup_view='after four existing compatibility contracts; original disk unchanged',
                result=f'PASS: {len(rows)} pinned game-pattern write envelopes are disjoint from {len(spans)} new code spans',
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
