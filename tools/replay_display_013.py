"""Replay the pinned menu compositor and 3D terminal viewport offline."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_EDI, UC_X86_REG_ESI, UC_X86_REG_ESP
from inspect_renderer import PATCH_SITES
from replay_display_012 import BATCH, FAKE_SCISSOR, FRAME, call_site, make_case, fmt32
from replay_gameplay_caption_events import SCRATCH
from replay_menu_tweaks import install
from replay_subtitle_layout import map_exact


NEW = {
    "terminal_rt_camera":"LayerCameraViewport",
    "menu_rt_allocate":"MenuAllocate",
    "menu_rt_width":"MenuLogicalWidth",
    "menu_rt_height":"MenuLogicalHeight",
    "menu_rt_u0":"MenuNormalizeU", "menu_rt_u1":"MenuNormalizeU",
    "menu_rt_v0":"MenuNormalizeV", "menu_rt_v1":"MenuNormalizeV",
}
GPU = FRAME + 0x40
VTABLE = FRAME + 0x400
SET_VIEWPORT = SCRATCH + 0x35000
TEXTURE_POINTER = FRAME + 0x900
TEXTURE_TABLE = FRAME + 0xa00
CAMERA = FRAME + 0xf00
PANEL = FRAME + 0x1100
MAP_ID, MENU_ID, OTHER_ID = 11, 12, 13


def run(exe, lib, mode):
    # Apply 012's existing terminal upscaling in all three modes. The changes
    # made in 013 are installed/restored on a separate Unicorn mapping only.
    g, _ = make_case(exe, lib, "modified")
    source = lib.with_suffix(".map").read_text(encoding="utf-8", errors="replace")
    symbols = {name:map_exact(source, "_" + name) for name in set(NEW.values())} if mode!="baseline" else {}
    spans = [(PATCH_SITES[key][0], bytes.fromhex(PATCH_SITES[key][1]), 0xe8, name) for key, name in NEW.items()]
    install(g, spans, mode, symbols)
    camera, clips, allocations = [], [], []
    g.w(0x8dd0f4, GPU)
    g.w(GPU, VTABLE)
    g.w(VTABLE+0xbc, SET_VIEWPORT)
    g.w(VTABLE+300, FAKE_SCISSOR)
    g.w(0x872278, TEXTURE_POINTER)
    g.w(TEXTURE_POINTER, TEXTURE_TABLE)
    g.w(0x970a70, 1)
    g.w(0x970a3c, MAP_ID)

    def boundary(address):
        sp = g.u.reg_read(UC_X86_REG_ESP)
        if address == 0x6164b0:
            allocations.append(struct.unpack("<IIII",g.u.mem_read(sp+4,16)))
            g.ret()
        elif address in (SET_VIEWPORT, FAKE_SCISSOR):
            ptr = g.rd(sp+8)
            if address==SET_VIEWPORT:
                camera.append(struct.unpack("<IIIIff",g.u.mem_read(ptr,24)))
            else:
                clips.append(struct.unpack("<IIII",g.u.mem_read(ptr,16)))
            g.ret()
            g.u.reg_write(UC_X86_REG_ESP,sp+12)
        elif address == 0x416a50:
            assert g.rd(sp+4)==0
            g.ret()
        else:
            return False
        return True

    g.extra_hook = boundary
    active = mode=="modified"
    side = 1024 if active else 512
    for width,height,slot,want in [(640,480,0x921b20,512),(3840,2160,FRAME,512),(3840,2160,0x921b20,side)]:
        g.w(0x872500,width,height)
        call_site(g,0x4b9529,(512,512,0,slot))
        assert allocations[-1]==(want,want,0,slot)

    # Native camera descriptor -> native 62EF30 -> new seam -> native 40F9A0
    # -> simulated device viewport. A matching scissor alone cannot fix XYZ.
    g.w(0x921b20,MENU_ID)
    for tex in (MENU_ID,OTHER_ID):
        tex_side = side if tex==MENU_ID else 1024
        g.u.mem_write(TEXTURE_TABLE+32*tex+0x18,struct.pack("<HHHH",tex_side,tex_side,tex_side,tex_side))
    geometry = []
    for name, target, raster, bounds, want in (
        ("map",MAP_ID,512,(0,0,256,256),(0,0,512 if active else 256,512 if active else 256)),
        ("map_inclusive_edge",MAP_ID,512,(0,0,257,257),(0,0,512 if active else 257,512 if active else 257)),
        ("map_subview",MAP_ID,512,(8,12,219,222),(16,24,438,444) if active else (8,12,219,222)),
        ("other",OTHER_ID,512,(8,12,219,222),(8,12,219,222)),
        ("map_low_res",MAP_ID,256,(0,0,256,256),(0,0,256,256)),
        ("map_physical",MAP_ID,512,(0,0,512,512),(0,0,512,512)),
        ("menu_background",MENU_ID,side,(0,0,513,449),(0,0,1024,898) if active else (0,0,512,449)),
    ):
        g.w(0x8da558,raster,raster,target)
        x,y,w,h=bounds
        g.w(CAMERA,x)
        g.w(CAMERA+0xc,w)
        g.w(CAMERA+0x14,y)
        g.w(CAMERA+0x20,h)
        g.w(CAMERA+0x38,64,32)
        g.w(0x8da570,3,5,20,25)
        original = bytes(g.u.mem_read(CAMERA,68))
        g.call(0x62ef30,(CAMERA,))
        assert camera[-1][:4]==want, (mode,name,camera[-1])
        assert 0.0<=camera[-1][5]<=camera[-1][4]<=1.0
        if active:
            assert clips[-1]==(3,5,21,26), clips[-1]
        assert bytes(g.u.mem_read(CAMERA,68))==original
        geometry.append([name,*camera[-1][:4]])

    # Native 4B5A30 packs input rect, output rect and sampled UVs.
    # 512x448 content must still sample 7/8 of the texture, not 7/16.
    g.w(0xA57190,0)
    g.w(0xA575F4,fmt32(4))
    g.w(0xA57740,fmt32(20),fmt32(30),fmt32(4))
    g.w(PANEL+0x48,MENU_ID)
    g.w(PANEL+0x4c,fmt32(256))
    g.w(PANEL+0x5c,fmt32(50),fmt32(50),fmt32(224))
    g.w(PANEL+0xe0,fmt32(0),fmt32(0),fmt32(512),fmt32(448))
    g.w(PANEL+0x100,fmt32(0))
    positions, texture, uvs = PANEL+0x200, PANEL+0x220, PANEL+0x240
    composite = []
    for name, crop, tid in (("cropped",1,MENU_ID),("full",0,MENU_ID),("other_full",0,OTHER_ID)):
        g.w(0xA56EDC,crop)
        g.w(PANEL+0x48,tid)
        g.call(0x4b5a30,(positions,),{UC_X86_REG_ESI:PANEL,UC_X86_REG_EDI:texture,UC_X86_REG_EBX:uvs})
        pos = struct.unpack("<4f",g.u.mem_read(positions,16))
        rect = struct.unpack("<4f",g.u.mem_read(texture,16))
        uv = struct.unpack("<4f",g.u.mem_read(uvs,16))
        logical = 1024 if tid==OTHER_ID else 512
        assert pos==(220.0,230.0,1244.0,1126.0), pos
        assert rect==(0,0,logical,448 if crop else logical), rect
        assert uv==(1/logical,1/logical,(rect[2]-2)/logical,(rect[3]-2)/logical), uv
        composite.append([name,list(rect),list(uv)])

    verts = (20.0,30.0,0.001,1.0,0.99,0.25,0.75)
    g.w(FRAME+0x48,FRAME+0x140)
    drawn = []
    for name,raster,target,fvf,factor in (
        ("menu",side,MENU_ID,0x144,2 if active else 1),
        ("other",1024,OTHER_ID,0x144,1),
        ("map_text",512,MAP_ID,0x144,2),
        ("map_3d",512,MAP_ID,0x142,1),
    ):
        g.w(0x8da558,raster,raster,target)
        g.w(0x8dafb4,7)
        g.w(0x8dc924+7*24,28)
        g.w(0x8dafa0,fvf)
        g.w(0x8dafb0,4)
        g.call(0x40de6e,regs={UC_X86_REG_EAX:BATCH},stop=0x40de73)
        g.u.mem_write(BATCH,struct.pack("<7f",*verts))
        g.w(0x8daf00,BATCH+28)
        g.w(0x8daf14,1)
        g.call(0x40e21b,regs={UC_X86_REG_EAX:FRAME+0x48},stop=0x40e220)
        assert bytes(g.u.mem_read(BATCH,28))==struct.pack("<7f",verts[0]*factor,verts[1]*factor,*verts[2:])
        drawn.append([name,20*factor,30*factor])
    # SetScissorRect only when the stored previous rectangle is different.
    g.w(0x8da558,side,side,MENU_ID)
    g.w(0x8da570,0,0,0,0)
    g.call(0x40d3a0,(0,0,511,447))
    assert clips[-1]==(0,0,side,896 if active else 448)
    return dict(mode=mode, game_launched=False, map_viewports=geometry, menu_side=side,
                menu_composite=composite, menu_clip=list(clips[-1]), written_xy=drawn,
                exe_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),
                asi_sha256=hashlib.sha256(lib.read_bytes()).hexdigest())


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe",type=Path,required=True)
    parser.add_argument("--library",type=Path,required=True)
    parser.add_argument("--mode",choices=["baseline","modified","rollback"],required=True)
    args=parser.parse_args()
    report=run(args.exe,args.library,args.mode)
    print(json.dumps(report,separators=(",",":")))
