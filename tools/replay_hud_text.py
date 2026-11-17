"""Run the native tutorial and selected-weapon text paths in isolated x86 memory."""
import argparse
import json
from pathlib import Path
import struct

from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ESP
from build_locale import encode
from inspect_renderer import PATCH_SITES
from replay_gameplay_caption_events import Replay, SCRATCH, TABLE, TEXT
from replay_subtitle_layout import map_exact


SITES = {
    'hud_hint_wrap_begin': 'HudHintWrapStart',
    'hud_hint_wrap_end': 'HudHintWrapEnd',
    'hud_hint_draw_begin': 'HudHintDrawStart',
    'hud_hint_draw_end': 'HudHintDrawEnd',
    'hud_weapon_begin': 'HudWeaponStart',
    'hud_weapon_wrap': 'HudWeaponWrap',
    'hud_weapon_end': 'HudWeaponEnd',
}


def run(exe, asi, mapfile, manifest, mode):
    meta=json.loads(manifest.read_text(encoding='utf-8'))
    glossary=meta['glyphs']
    hint=encode(meta['targets']['bs']['2447'].replace('%2','鼠标左键'),glossary)
    weapon=encode(meta['targets']['bs']['445'],glossary)
    rows=[]
    for width,height in ((640,480),(1920,1080),(3840,2160)):
        game=Replay(exe,asi,mapfile)
        for key,name in SITES.items():
            address,hex_bytes=PATCH_SITES[key]
            original=bytes.fromhex(hex_bytes)
            if bytes(game.u.mem_read(address,5))!=original: raise ValueError(f'{key}: original bytes')
            if mode!='baseline':
                entry=map_exact(mapfile.read_text(encoding='utf-8'),'_'+name)
                game.branch(address,entry,b'\xe8')
                if mode=='rollback':
                    game.u.mem_write(address,original)
                    if bytes(game.u.mem_read(address,5))!=original: raise ValueError(f'{key}: rollback bytes')

        game.w(0x872500,width,height)
        game.w(SCRATCH+0x18000,0,width-1,width//2,width,0,0,height-1)
        game.w(0xa05b60,20,20,20,20)
        game.w(0x872278,SCRATCH+0x22000)
        game.w(SCRATCH+0x22000,SCRATCH+0x22100)
        game.w(SCRATCH+0x22118,64|(64<<16))
        game.w(TABLE+445*4,TEXT+0x4000)
        game.u.mem_write(TEXT,hint+b'\0')
        game.u.mem_write(TEXT+0x4000,weapon+b'\0')
        captured=[]
        wrap_scales=[]
        def intercept(address):
            if address==0x611C70:
                style=game.rd(0x9e88ac)
                wrap_scales.append(struct.unpack('<2f',game.u.mem_read(style+8,8)))
                return False
            if address in (0x4ad350,0x40fc20,0x412dc0,0x7b397a):
                game.ret(0)
                return True
            if address!=0x613260:
                return False
            esp=game.u.reg_read(UC_X86_REG_ESP)
            x,y,ptr,color,alpha=struct.unpack('<ffIII',game.u.mem_read(esp+4,20))
            style=game.rd(0x9e88ac)
            sx,sy=struct.unpack('<2f',game.u.mem_read(style+8,8))
            raw=bytes(game.u.mem_read(ptr,512)).split(b'\0',1)[0]
            captured.append(dict(x=x,y=y,sx=sx,sy=sy,text=raw.hex(),color=color,alpha=alpha))
            game.ret(0)
            return True
        game.extra_hook=intercept
        style0=[game.rd(a) for a in (0x9E88A4,0x9E88A8,0x9E88AC)]
        style_table=bytes(game.u.mem_read(0x8BA920,28*32))
        game.call(0x62FE80,(100,),{UC_X86_REG_EAX:TEXT})
        wrapped=bytes(game.u.mem_read(0x9f4900,512)).split(b'\0',1)[0]
        game.w(0x9f4d04,1,1,max(0,len(wrapped)-1))
        game.call(0x630080)
        game.w(0x964b80,0,0)
        game.w(0x964fc4,0)
        game.w(0x964b58,0)
        game.w(0x875e80,0)
        game.call(0x57b700,(0x964b80,0,52,height-60,127))
        game.w(0x875e80,9)
        game.call(0x57b700,(0x964b80,0,160,height-60,127))
        restored=style0==[game.rd(a) for a in (0x9E88A4,0x9E88A8,0x9E88AC)]
        assert restored and style_table==bytes(game.u.mem_read(0x8BA920,28*32))
        assert wrapped.replace(b'\n',b'')==hint
        assert len(captured)==3 and bytes.fromhex(captured[0]['text']).replace(b'\n',b'')==hint
        assert all(bytes.fromhex(a['text'])==weapon for a in captured[1:])
        assert len(wrap_scales)==2
        assert all(0<=a['x']<width and 0<=a['y']<height for a in captured)
        expected=max(1.0,height/720)
        original_font_y=struct.unpack_from('<f',style_table,18*28+12)[0]
        good=(abs(captured[0]['sy']-expected)<1e-5
              and all(abs(a['sy']-original_font_y*expected)<1e-5 for a in captured[1:])
              and abs(wrap_scales[0][1]-captured[0]['sy'])<1e-5
              and abs(wrap_scales[1][1]-captured[-1]['sy'])<1e-5)
        rows.append(dict(width=width,height=height,wrap_scales=wrap_scales,draws=captured,font_restored=restored,passed=good))
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ('exe','asi','map','manifest','out'):
        parser.add_argument('--'+field,type=Path,required=True)
    parser.add_argument('--mode',required=True,choices=('baseline','modified','rollback'))
    a=parser.parse_args()
    rows=run(a.exe,a.asi,a.map,a.manifest,a.mode)
    a.out.write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
    n=sum(bool(r['passed']) for r in rows)
    print(f'HUD TEXT {"PASS" if n==len(rows) else "FAIL"}: {n}/{len(rows)}; '
          f'4K hint style.y={rows[-1]["draws"][0]["sy"]:.3f}; '
          f'4K weapon style.y={rows[-1]["draws"][1]["sy"]:.3f}; original font restored')
    raise SystemExit(n!=len(rows))
