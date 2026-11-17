"""Offline replay of pinned x86 game instructions and built ASIs, not a game run."""
import argparse
from pathlib import Path
import re
import struct

import pefile
from unicorn.x86_const import (
    UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_EBP, UC_X86_REG_EFLAGS,
    UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EIP, UC_X86_REG_ESP, UC_X86_REG_FPSW,
)
from replay_gameplay_caption_events import Replay, SCRATCH, STACK, STOP, TEXT
from replay_subtitle_layout import map_exact


ROOT = Path(__file__).resolve().parents[1]
MENU = {
    0x4B758A: bytes.fromhex("e8c1b71500"),
    0x4BF717: bytes.fromhex("e834361500"),
}
ENERGY = (
    ("TweakPower856", UC_X86_REG_EDI), ("TweakPower9bf", UC_X86_REG_EDI),
    ("TweakPowerc56", UC_X86_REG_EBP), ("TweakPowerd9f", UC_X86_REG_EDI),
    ("TweakPower0df", UC_X86_REG_EBP), ("TweakPower693", UC_X86_REG_EBX),
    ("TweakPower751", UC_X86_REG_ESI), ("TweakPowerf02", UC_X86_REG_ESI),
)
TARGETS = ("TweakHpNormal", "TweakHpAlt", *(n for n, _ in ENERGY), "TweakPerception", "TweakTick")


def tweak_spans():
    content = (ROOT / "src/gameplay_tweaks_sites.h").read_text(encoding="utf-8-sig")
    rows = re.findall(r'\{(0x[0-9a-f]+),(\d+),\{([^}]+)\}(?:,(0x[0-9a-f]+))?\}', content)
    if len(rows) != len(TARGETS):
        raise ValueError("unexpected tweak site count")
    result = []
    for (a, n, octets, opcode), function in zip(rows, TARGETS):
        native = bytes(int(b, 0) for b in octets.split(","))
        if len(native) != int(n):
            raise ValueError("signature length mismatch")
        result.append((int(a, 0), native, int(opcode or "0xe9", 0), function))
    return result


def map_asi(case, path, names):
    pe = pefile.PE(str(path))
    layout = path.with_suffix(".map").read_text(encoding="utf-8", errors="replace")
    stamp = re.search(r'Timestamp is ([0-9A-Fa-f]+)', layout)
    if pe.FILE_HEADER.Machine != 0x14c or not stamp or int(stamp[1], 16) != pe.FILE_HEADER.TimeDateStamp:
        raise ValueError(f"ABI or MAP/ASI mismatch: {path}")
    base = pe.OPTIONAL_HEADER.ImageBase
    case.u.mem_map(base, (pe.OPTIONAL_HEADER.SizeOfImage + 4095) & ~4095)
    case.u.mem_write(base, pe.get_memory_mapped_image())
    return {name: map_exact(layout, "_" + name) for name in names}


def install(case, spans, mode, symbols):
    for a, native, _, _ in spans:
        assert case.u.mem_read(a, len(native)) == native, hex(a)
    if mode != "baseline":
        for a, native, opcode, name in spans:
            case.branch(a, symbols[name], bytes([opcode]), len(native))
        assert all(case.u.mem_read(a, len(native)) != native for a, native, _, _ in spans)
    if mode == "rollback":
        for a, native, _, _ in spans:
            case.u.mem_write(a, native)
        assert all(case.u.mem_read(a, len(native)) == native for a, native, _, _ in spans)


def fmt32(n):
    return struct.unpack("<I", struct.pack("<f", n))[0]


def menu(exe, lib, mode):
    replay = Replay(exe)
    symbol = map_asi(replay, lib, ("MenuContrastDraw",))
    install(replay, [(a, b, 0xe8, "MenuContrastDraw") for a, b in MENU.items()], mode, symbol)
    draw = []
    def boundary(address):
        if address != 0x612c10:
            return False
        sp = replay.u.reg_read(UC_X86_REG_ESP)
        read = replay.rd
        draw.append((read(read(sp+4)), read(read(sp+8)), read(sp+12), read(sp+16), read(sp+20), read(0x9e3688)))
        # Treat the very next GPU/text raster path as a boundary. Also confirm
        # the next pass uses the right x/y even if the draw mutates them.
        replay.w(read(sp+4), fmt32(123))
        replay.w(read(sp+8), fmt32(456))
        replay.ret()
        return True
    replay.extra_hook = boundary
    initial = fmt32(380), fmt32(150), fmt32(1120)
    fg, bg = 0xffffff80, 0x00000080
    formatted = b'Graphics \x1f0001\x1f0002\0'
    n_menu = None
    for address, as_call in [*((a, True) for a in MENU), (0x612d50, False)]:
        for sample in (formatted, b"3840 x 2160 144Hz\0", b"bad\x1f00010\0"):
            draw.clear()
            replay.u.mem_write(TEXT+0x7000, sample)
            args = (*initial, TEXT+0x7000, fg, bg)
            replay.w(0x9e3688, 7)
            if as_call:
                assert replay.u.mem_read(address, 1)==b'\xe8'
                replay.w(STACK, *args)
                replay.u.reg_write(UC_X86_REG_ESP, STACK)
                replay.u.emu_start(address, address+5, count=50000)
                assert replay.u.reg_read(UC_X86_REG_EIP)==address+5
            else:
                replay.call(address,args)
            reduced = as_call and sample==formatted and mode=="modified"
            assert len(draw)==(2 if reduced else 5), (hex(address), draw)
            assert draw[-1]==(*args[:-1],0), draw[-1]
            assert all(row[2:]==(initial[2],TEXT+0x7000,bg,1) for row in draw[:-1])
            if reduced:
                assert draw[0][:2]==(fmt32(381),fmt32(151))
            assert replay.rd(0x9e3688)==(7 if reduced else 0)
            if as_call and sample==formatted:
                n_menu=len(draw)
    return n_menu


def tweaks(exe, lib, mode):
    case = Replay(exe)
    symbols = map_asi(case, lib, (*TARGETS,"TweakOptions"))
    spans = tweak_spans()
    install(case, spans, mode, symbols)
    active = mode=="modified"
    by_name = {name:(a,len(native)) for a,native,_,name in spans}
    ctx, player, npc, observer, aux = (SCRATCH + x for x in (0x30000,0x33000,0x36000,0x39000,0x3c000))
    case.w(0xa1d604,ctx)
    case.w(ctx+0x20,player)
    case.f(player+0x20c,100)
    case.f(npc+0x20c,120)
    case.f(ctx+0xee8,80)
    cost, code = aux, aux+0x100
    def step(name, reg, obj, amount, next_fpu=False):
        a, size = by_name[name]
        case.f(cost, amount)
        # Exact x87 load upper argument, then game instruction(s).
        case.u.mem_write(code,b'\xdb\xe3\xd9\x05'+struct.pack("<I",cost))
        case.branch(code+8,a,b'\xe9')
        case.u.ctl_remove_cache(code,code+13)
        case.u.reg_write(UC_X86_REG_EFLAGS,0x246)
        case.call(code,regs={reg:obj, **({UC_X86_REG_EDI:9} if name=="TweakPower0df" else {})},stop=a+size)
        if name=="TweakPower0df":
            assert case.u.reg_read(UC_X86_REG_EDI)==0
        assert case.u.reg_read(UC_X86_REG_EFLAGS)&0x40
        assert (case.u.reg_read(UC_X86_REG_FPSW)>>11)&7==(7 if next_fpu else 0)
        if next_fpu:
            store = b'\xd9\x1d'+struct.pack("<I",cost)+b'\xc3'
            case.u.mem_write(code+32,store);case.call(code+32)
            return case.rd(cost)
        return None
    def options(bits):
        case.w(symbols["TweakOptions"],bits)
    health = []
    for name in TARGETS[:2]:
        for on,target,initial,expected in [(0,player,40,-12),(1,player,40,100 if active else -12),
                                           (1,npc,75,-12),(1,player,0,-12)]:
            options(on)
            case.f(target+0x208,initial)
            step(name,UC_X86_REG_EAX,target,-12)
            assert case.rd(target+0x208)==fmt32(expected), (name,target,case.rd(target+0x208))
            if on and target==player and initial:
                health.append(expected)
    case.f(player+0x208,100)
    energy = []
    for name,reg in ENERGY:
        for on,obj,expected in [(0,ctx+0xec8,32),(2,ctx+0xec8,80 if active else 32),(2,npc+0xec8,32)]:
            options(on)
            case.f(obj+0x18,40)
            st0=step(name,reg,obj,8,name=="TweakPower751")
            assert case.rd(obj+0x18)==fmt32(expected), (name,hex(obj),case.rd(obj+0x18))
            if st0 is not None:
                assert st0==fmt32(expected)
            if on and obj==ctx+0xec8:
                energy.append(expected)
    # The two out-of-scope native calculation/notification boundaries below
    # use fixtures; the actual detection mask computation still executes.
    observer_record=observer+0x400
    case.w(observer+0xbc,observer_record)
    case.w(observer_record+4,observer)
    for obj in (player,npc):
        case.w(obj+8,8)
        case.w(obj+0xbc,obj+0x400)
    case.w(player+0x19c,ctx)
    sensor=aux+0x800
    case.f(sensor,20)
    case.f(sensor+0x14,1)
    hit=[]
    def boundary(address):
        if address==0x5cfbc0:
            hit.append("tick")
            case.ret()
        elif address==0x488a40:
            case.ret(1)
        elif address==0x479740:
            esp=case.u.reg_read(UC_X86_REG_ESP)
            case.f(case.rd(esp+16),1)
            case.f(case.rd(esp+20),1)
            case.ret()
        else:
            return False
        return True
    case.extra_hook=boundary
    masks=[]
    for bits,target,expected in [(0,player,1),(4,player,0 if active else 1),(4,npc,1),(0,player,1)]:
        options(bits)
        case.call(0x48d7c0,(observer,target,0x4004,sensor))
        mask=case.u.reg_read(UC_X86_REG_EAX)
        assert mask==expected, (bits,hex(target),mask)
        masks.append(mask)
    options(3)
    case.f(player+0x208,40)
    case.f(ctx+0xee0,0)
    case.call(0x545430,stop=0x545435)
    assert hit==["tick"]
    assert case.rd(ctx+0xee0)==fmt32(80 if active else 0)
    assert case.rd(player+0x208)==fmt32(100 if active else 40)
    # Disable all three: no sticky feature flags or non-player effects.
    options(0)
    case.f(player+0x208,20)
    case.f(ctx+0xee0,4)
    case.call(0x545430,stop=0x545435)
    assert case.rd(player+0x208)==fmt32(20) and case.rd(ctx+0xee0)==fmt32(4)
    return health,energy,masks


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--exe",required=True,type=Path)
    p.add_argument("--runtime",required=True,type=Path)
    p.add_argument("--mode",required=True,choices=("baseline","modified","rollback"))
    args=p.parse_args()
    menu_passes=menu(args.exe,args.runtime/"SecondSight.Localization.asi",args.mode)
    hp_results,power_results,detection=tweaks(args.exe,args.runtime/"SecondSight.GameplayTweaks.asi",args.mode)
    print(f"{args.mode.upper()} PASS: menu={menu_passes} draws; ASCII/non-menu=5; damage={hp_results}; "
          f"power={power_results}; detection={detection}; no game launched")
