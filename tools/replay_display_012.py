"""Replay 012 native chapter, selected-label and terminal-raster seams, without the game."""
import argparse
import json
from pathlib import Path
import struct

from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ESP, UC_X86_REG_EIP
from build_locale import encode
from inspect_renderer import PATCH_SITES
from replay_gameplay_caption_events import Replay, SCRATCH, TEXT, TABLE, STACK
from replay_menu_tweaks import map_asi, install
from replay_subtitle_layout import map_exact

SYMBOLS = {
    "chapter_card_begin": ("ChapterCardStart", 0xe8),
    "chapter_card_end": ("ChapterCardEnd", 0xe8),
    "selection_draw": ("HudSelectionDraw", 0xe8),
    "terminal_rt_allocate": ("MapAllocate", 0xe8),
    "terminal_rt_batch_begin": ("MapRememberHook", 0xe9),
    "terminal_rt_batch_scale": ("MapScaleHook", 0xe9),
    "terminal_rt_scissor": ("MapScissor", 0xe9),
    # The 011 operations are part of the starting point in all three modes.
    "hud_weapon_begin": ("HudWeaponStart", 0xe8),
    "hud_weapon_end": ("HudWeaponEnd", 0xe8),
}
STYLE = (0x9e88a4, 0x9e88a8, 0x9e88ac)
BATCH = SCRATCH + 0x31000
FAKE_UNLOCK = SCRATCH + 0x32000
FAKE_SCISSOR = SCRATCH + 0x33000
FRAME = SCRATCH + 0x34000

def fmt32(value):
    return struct.unpack('<I',struct.pack('<f',value))[0]

def call_site(case,address,args):
    case.w(STACK,*args)
    case.u.reg_write(UC_X86_REG_ESP,STACK)
    case.u.emu_start(address,address+5,count=500000)
    assert case.u.reg_read(UC_X86_REG_EIP)==address+5

def make_case(exe, lib, mode):
    g = Replay(exe)
    mapped = map_asi(g,lib,tuple(name for name,_ in SYMBOLS.values()))
    spans = [(PATCH_SITES[key][0],bytes.fromhex(PATCH_SITES[key][1]),opcode,symbol)
             for key,(symbol,opcode) in SYMBOLS.items()]
    install(g,spans[-2:], "modified",mapped)
    install(g,spans[:-2],mode,mapped)
    if mode=="modified":
        scissor=spans[-3]
        layout=lib.with_suffix('.map').read_text(encoding='utf-8',errors='replace')
        trampoline=SCRATCH+0x9000
        g.trampoline(scissor[0],trampoline,scissor[1])
        g.w(map_exact(layout,'?originalScissor@@3P6AXHHHH@ZA'),trampoline)
    return g,mapped

def replay_text(exe,lib,mode,meta):
    g,mapped=make_case(exe,lib,mode)
    chapter=encode(meta['targets']['bs']['776'],meta['glyphs'])
    power=encode(meta['targets']['bs']['697'],meta['glyphs'])
    g.u.mem_write(TEXT+0x4100,chapter+b'\0')
    g.u.mem_write(TEXT+0x4200,power+b'\0')
    g.w(TABLE+776*4,TEXT+0x4100)
    g.w(0xa2beec,0)
    g.w(0x8963cc,776)
    g.w(0x8da574,0)
    g.f(FRAME+8,0.25)
    g.w(0xa05b60,20)
    original=[g.rd(a) for a in STYLE]
    orig_table=bytes(g.u.mem_read(0x8ba920,28*32))
    entry=[]
    active=mode=='modified'
    def hook(address):
        if address==0x584ec0:
            g.ret(FRAME)
        elif address in (0x613330,0x613260):
            sp=g.u.reg_read(UC_X86_REG_ESP)
            x,y,ptr,fg,bg=struct.unpack('<ffIII',g.u.mem_read(sp+4,20))
            active_style=g.rd(STYLE[2])
            sy=struct.unpack('<f',g.u.mem_read(active_style+12,4))[0]
            text=bytes(g.u.mem_read(ptr,512)).split(b'\0',1)[0]
            entry.append((x,y,sy,text,fg,bg))
            g.ret()
        else:
            return False
        return True
    g.extra_hook=hook
    results=[]
    for width,height in ((640,480),(1920,1080),(3840,2160)):
        g.w(0x872500,width,height)
        g.w(0x8da57c,height)
        g.call(0x5443b0)
        x,y,sy,text,fg,bg=entry.pop()
        assert text==chapter, text
        base=struct.unpack_from('<f',orig_table,24*28+12)[0]
        assert abs(sy-base*(max(1,height/720) if active else 1))<1e-5, (height,sy)
        assert 0<=y<height and x==25.0 and fg&0xff and bg&0xff
        assert [g.rd(a) for a in STYLE]==original
        # The same label rendered near the bottom boundary, with the exact
        # native 0x57BAEB call/ABI and the earlier 011 enlarged style.
        g.call(mapped["HudWeaponStart"],(18,))
        g.f(0x8baca0,1)
        bottomY=height-7
        call_site(g,0x57baeb,(fmt32(108),fmt32(bottomY),TEXT+0x4200,0x8080807f,0x7f))
        hx,hy,hsy,label,col,alpha=entry.pop()
        assert label==power and col==0x8080807f and alpha==0x7f and hx==108
        assert ((0<=hy<bottomY-4) if active else (hy==bottomY)), (height,hy)
        assert g.rd(0x8baca0)==fmt32(1)
        g.call(mapped["HudWeaponEnd"],(original[0],))
        assert [g.rd(a) for a in STYLE]==original and bytes(g.u.mem_read(0x8ba920,28*32))==orig_table
        results.append(dict(height=height, chapter_scale=sy, chapter_y=y, hud_y=hy, hud_scale=hsy))
    g.f(FRAME+8,300)
    g.call(0x5443b0)
    assert not entry and [g.rd(a) for a in STYLE]==original
    return results

def replay_terminal(exe,lib,mode):
    g,_=make_case(exe,lib,mode)
    advanced=mode=='modified'
    render=512 if advanced else 256
    allocation,rectangles=[],[]
    g.w(0x970a70,1)
    g.w(0x970a3c,-1)
    g.w(0x8dd0f4,FRAME+0x40)
    g.w(FRAME+0x40,FRAME+0x400)
    g.w(FRAME+0x400+300,FAKE_SCISSOR)
    g.w(FRAME+0x48,FRAME+0x140)
    g.w(FRAME+0x140+0x30,FAKE_UNLOCK)
    def hook(address):
        sp=g.u.reg_read(UC_X86_REG_ESP)
        if address==0x4134e0:
            args=tuple(g.rd(sp+i) for i in (4,8,12))
            allocation.append(args)
            if args[2]==0x970a3c:
                g.w(args[2],11)
            g.ret()
        elif address==FAKE_SCISSOR:
            ptr=g.rd(sp+8)
            rectangles.append(tuple(g.rd(ptr+i) for i in (0,4,8,12)))
            g.ret()
            # stdcall cleans the device and RECT arguments only: diagnostics
            # pushed by the game are cleaned by the game's own caller.
            g.u.reg_write(UC_X86_REG_ESP,sp+12)
        else:
            return False
        return True
    g.extra_hook=hook
    for w,h,slot,expected in [(640,480,0x970a3c,256),(3840,2160,FRAME,256),
                              (3840,2160,0x970a3c,render)]:
        g.w(0x872500,w,h)
        call_site(g,0x5ce45b,(256,256,slot))
        assert allocation[-1]==(expected,expected,slot)
    # Coordinate proof: CPU scales positions and keeps the remaining fields;
    # a different render target and XYZ format must not change at all.
    vertices=(3.0,6.0,0.001,1.0,0.99,0.25,0.75, 100.0,230.0,0.001,1.0,0.88,0.5,0.8)
    stride=28
    for field,rt,fvf,expected in [
        ('terminal',11,0x144,2 if advanced else 1),('other',12,0x144,1),('xyz',11,0x142,1)
    ]:
        g.w(0x8da558,render,render,rt)
        g.w(0x8dafb4,7)
        g.w(0x8dc924+7*24,stride)
        g.w(0x8dafa0,fvf)
        g.w(0x8dafb0,4)
        g.w(0x8daf14,0)
        g.call(0x40de6e,regs={UC_X86_REG_EAX:BATCH},stop=0x40de73)
        assert g.rd(0x8daf00)==BATCH
        g.u.mem_write(BATCH,struct.pack('<14f',*vertices))
        g.w(0x8daf00,BATCH+2*stride)
        g.w(0x8daf14,2)
        g.call(0x40e21b,regs={UC_X86_REG_EAX:FRAME+0x48},stop=0x40e220)
        g.u.ctl_remove_cache(0x40de6e,0x40de73)
        vals=list(vertices)
        for i in (0,1,7,8):vals[i]*=expected
        assert g.u.mem_read(BATCH,2*stride)==struct.pack('<14f',*vals),field
        assert g.rd(g.u.reg_read(UC_X86_REG_ESP))==FRAME+0x140
    g.w(0x8da558,render,render,11)
    g.call(0x40d3a0,(4,5,248,249))
    factor=2 if advanced else 1
    assert rectangles[-1]==(4*factor,5*factor,249*factor,250*factor)
    g.call(0x40d3a0,(0,0,render,render))
    assert rectangles[-1]==(0,0,render,render)
    g.w(0x8da558,render,render,12)
    g.call(0x40d3a0,(4,5,248,249))
    assert rectangles[-1]==(4,5,249,250)
    return render,rectangles

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('exe','library','manifest','out'):
        p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--mode',required=True,choices=('baseline','modified','rollback'))
    a=p.parse_args()
    m=json.loads(a.manifest.read_text(encoding='utf-8'))
    rows=replay_text(a.exe,a.library,a.mode,m)
    rt,rectangles=replay_terminal(a.exe,a.library,a.mode)
    a.out.write_text(json.dumps(dict(mode=a.mode,rows=rows,terminal=rt,rectangles=rectangles),indent=2)+'\n')
    print(f'{a.mode.upper()} PASS: chapter scale={rows[-1]["chapter_scale"]:.2f}; '
          f'4K HUD y={rows[-1]["hud_y"]:.0f}; terminal raster={rt}x{rt}; original font restored; game not launched')
