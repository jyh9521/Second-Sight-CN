"""Replay the recorded no-handle caption route and check for panel draws offline."""
import argparse
import json
from pathlib import Path

from build_locale import encode
from replay_gameplay_caption_events import Replay, OWNER, TABLE, TEXT, SCRATCH


def run(exe, library, symbols, manifest):
    results=[]
    data=json.loads(manifest.read_text(encoding='utf-8'))
    entry=encode(data['targets']['bs']['2491'],data['glyphs'])
    for flags, handle, remaining, eligible in (
        (14,-1,3.616934,True), (8,-1,3.616934,True),
        (4,-1,3.616934,False), (14,-1,0.0,False),
        (14,-2,3.616934,False), (14,0,3.616934,False),
        (4,7,3.616934,True),
    ):
        r=Replay(exe,library,symbols)
        r.text_addresses[2491]=TEXT
        r.u.mem_write(TEXT,entry+b'\0')
        r.w(TABLE+2491*4,TEXT)
        r.w(0x872500,3840,2160)
        r.w(SCRATCH+0x18000,0,0,1920,3840,0,0,2160)
        r.owner(bs=2491,handle=handle,flags=flags,priority=8)
        r.f(OWNER+0x18,remaining)
        # No original cue in this fixture: isolate the new renderer from native
        # fade/special layout. This is not recovery of the dump's screen pixels.
        if flags==8:
            r.event(2)  # native dispatcher selects it for the first time
        elif remaining>0 and handle in (-1,7) and flags!=4:
            r.update()  # real duration-driven speech event
        else:
            r.event(2)
        r.render()
        overlays=r.executed.get('GameplayCaptionDrawHook',0)-r.executed.get('nativeCaptionRenderer',0)
        panels=r.boundaries.get('gpu_background',0)
        drawn=[row['payload_hex'] for row in r.draws]
        good=(overlays==int(eligible) and panels==0 and
              drawn==([entry.hex()] if eligible else []))
        if eligible:
            # A real lifecycle-end event must remove the independent caption.
            r.end(3)
            r.w(0x9FE868,0) # isolate the independent state from native fade-out
            r.render()
            good=good and len(r.draws)==1
        results.append(dict(flags=flags,handle=handle,remaining=remaining,overlays=overlays,
                            panels=panels,draw_count=len(drawn),passed=good))
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('exe','library','map','manifest','out'):
        p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args()
    rows=run(a.exe,a.library,a.map,a.manifest)
    a.out.write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
    count=sum(row['passed'] for row in rows)
    print(f'CAPTION POLISH {"PASS" if count==len(rows) else "FAIL"}: {count}/{len(rows)}; dump-route overlays={rows[0]["overlays"]}; ready-voice panels={rows[-1]["panels"]}')
    raise SystemExit(count!=len(rows))
