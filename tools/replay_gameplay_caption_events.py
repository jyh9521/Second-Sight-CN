"""Hash-bound native x86 speech lifecycle replay; never launches the game.

The actual 456610 dispatcher, 457030 updater, 4566C0 ending and 63F600 reset
execute in Unicorn. Audio-device status, spatial volume and GPU submission are
explicit controlled boundaries. A ready, playing voice whose native display
gate is zero is the negative control, not a claim about a captured user process.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import struct

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *

EXPECTED = '4092a8d1fb042dffe9fb95e2185f32cb80390299145e8d453a5e909a06d35fda'
BASE = 0x400000
SCRATCH = 0x20000000
STACK = SCRATCH + 0xFF000
STOP = SCRATCH + 0x80
CALLBACK = SCRATCH + 0x100
OWNER = SCRATCH + 0x1000
NODE = SCRATCH + 0x2000
TABLE = SCRATCH + 0x4000
TEXT = SCRATCH + 0xC000
DISPATCH = 0x456610
RENDER_CALL = 0x63D78A
RESET_CALL = 0x63D494
SIGNATURES = {
    DISPATCH: bytes.fromhex('85c0578bfa'),
    RENDER_CALL: bytes.fromhex('e8a1200000'),
    RESET_CALL: bytes.fromhex('e867210000'),
}


class Replay:
    def __init__(self, exe, library=None, map_path=None, rollback=False, glyphs=2, baseline_with_library=False):
        data = exe.read_bytes()
        if hashlib.sha256(data).hexdigest() != EXPECTED:
            raise ValueError('unsupported executable identity')
        pe = pefile.PE(data=data)
        self.u = u = Uc(UC_ARCH_X86, UC_MODE_32)
        u.mem_map(BASE, (pe.OPTIONAL_HEADER.SizeOfImage + 4095) & ~4095)
        u.mem_write(BASE, pe.get_memory_mapped_image())
        u.mem_map(SCRATCH, 0x100000)
        self.events = []
        self.callbacks = []
        self.draws = []
        self.boundaries = {}
        self.audio_ready = True
        self.audio_active = True
        self.extra_hook = None
        self.symbols = {}
        self.executed = {}
        self.rollback_bytes_verified = False
        self.heap_next = 0x21000000
        self.payloads = {2473: b'\x1f0001' * glyphs, 2508: b'\x1f0002' * glyphs}
        self.text_addresses = {2473: TEXT, 2508: TEXT + 0x2000}
        self.w(0x8BB378, 1)
        self.f(0x8BB380, 1)
        self.w(0x91C88C, 1)
        self.w(0x90A338, TABLE)
        self.w(TABLE + 2473 * 4, TEXT)
        self.w(TABLE, TEXT + 0x100)
        u.mem_write(TEXT, self.payloads[2473] + b'\0')
        u.mem_write(TEXT + 0x2000, self.payloads[2508] + b'\0')
        self.w(TABLE + 2508 * 4, TEXT + 0x2000)
        self.w(TABLE, TEXT + 0x4000)
        self.w(0x872500, 2880, 1800)
        self.w(0x8AA0E8, 1)
        self.w(0xA0A628, SCRATCH + 0x18000)
        self.w(SCRATCH + 0x18000, 0, 0, 1440, 2880, 0, 0, 1800)
        self.w(0x9E88A4, 24)
        self.w(0x9E88A8, 0x8BA860)
        self.w(0x9E88AC, 0x8BABC0)
        self.w(0x9E88A0, 1)
        self.f(SCRATCH + 0x200, 1)
        # Spatial volume is a synthetic boundary returning ST(0)=1.0.
        u.mem_write(0x456AC0, b'\xd9\x05' + struct.pack('<I', SCRATCH + 0x200) + b'\xc3')
        for address, expected in SIGNATURES.items():
            if bytes(u.mem_read(address, len(expected))) != expected:
                raise ValueError(f'native signature mismatch {address:#x}')
        u.hook_add(UC_HOOK_CODE, self.hook)
        if library:
            self.install_library(library, map_path, rollback, baseline_with_library)

    def install_library(self, library, map_path, rollback, baseline_with_library):
        from replay_subtitle_layout import map_exact
        if not map_path:
            raise ValueError('--library requires --map')
        dll = pefile.PE(str(library))
        if dll.FILE_HEADER.Machine != 0x14C:
            raise ValueError('library must be x86')
        symbols = map_path.read_text(encoding='utf-8', errors='replace')
        stamp = re.search(r'Timestamp is ([0-9A-Fa-f]+)', symbols)
        if not stamp or int(stamp.group(1), 16) != dll.FILE_HEADER.TimeDateStamp:
            raise ValueError('MAP timestamp does not match supplied ASI')
        base = dll.OPTIONAL_HEADER.ImageBase
        self.u.mem_map(base, (dll.OPTIONAL_HEADER.SizeOfImage + 4095) & ~4095)
        self.u.mem_write(base, dll.get_memory_mapped_image())
        names = {name: '_' + name for name in ('GameplayCaptionEventHook', 'GameplayCaptionOriginal',
                  'GameplayCaptionObserve', 'GameplayCaptionLookup', 'GameplayCaptionDrawHook', 'GameplayCaptionResetHook')}
        names.update(wrapHook='?wrapHook@@YAPADPBDM@Z', originalWrap='?originalWrap@@3P6APADPBDM@ZA',
                     initializer='??__EwrapBuffers@@YAXXZ', malloc='__malloc_base', free='__free_base', atexit='_atexit')
        self.symbols = {name: map_exact(symbols, target) for name, target in names.items()}
        for name, value in self.symbols.items():
            if not base <= value < base + dll.OPTIONAL_HEADER.SizeOfImage:
                raise ValueError(f'MAP symbol {name} outside ASI')
        # Retain the production text transport in baseline and rollback as well.
        for address in (0x610A96, 0x6119F3, 0x611A59, 0x611D1B, 0x611D58, 0x612561):
            if bytes(self.u.mem_read(address, 2)) != b'\x3c\x2c':
                raise ValueError(f'marker signature mismatch {address:#x}')
            self.u.mem_write(address + 1, b'\x1f')
        self.u.mem_map(0, 0x1000)
        self.w(0, -1)  # Synthetic x86 SEH/TEB boundary; no Windows execution.
        self.u.mem_map(0x21000000, 0x01000000)
        wrap_entry = 0x611C70
        wrap_prologue = bytes.fromhex('81ec04020000')
        if bytes(self.u.mem_read(wrap_entry, 6)) != wrap_prologue:
            raise ValueError('wrap signature mismatch')
        self.trampoline(wrap_entry, SCRATCH + 0x80000, wrap_prologue)
        self.w(self.symbols['originalWrap'], SCRATCH + 0x80000)
        self.branch(wrap_entry, self.symbols['wrapHook'], b'\xe9', 6)
        self.trampoline(DISPATCH, SCRATCH + 0x81000, SIGNATURES[DISPATCH])
        self.w(self.symbols['GameplayCaptionOriginal'], SCRATCH + 0x81000)
        if not baseline_with_library:
            self.branch(DISPATCH, self.symbols['GameplayCaptionEventHook'], b'\xe9')
            self.branch(RENDER_CALL, self.symbols['GameplayCaptionDrawHook'], b'\xe8')
            self.branch(RESET_CALL, self.symbols['GameplayCaptionResetHook'], b'\xe8')
        if rollback:
            # A real rollback on this independent mapped copy: first install the
            # same new branches, then restore and verify all three original sites.
            for address, expected in SIGNATURES.items():
                self.u.mem_write(address, expected)
            self.rollback_bytes_verified = all(bytes(self.u.mem_read(a, len(b))) == b
                                               for a, b in SIGNATURES.items())
        self.call(self.symbols['initializer'])

    def branch(self, address, target, opcode, size=5):
        self.u.mem_write(address, opcode + struct.pack('<i', target - address - 5) + b'\x90' * (size - 5))

    def trampoline(self, address, target, prologue):
        self.u.mem_write(target, prologue)
        self.branch(target + len(prologue), address + len(prologue), b'\xe9')

    def w(self, address, *values):
        self.u.mem_write(address, struct.pack('<' + 'I' * len(values), *(x & 0xFFFFFFFF for x in values)))

    def f(self, address, value):
        self.u.mem_write(address, struct.pack('<f', value))

    def rd(self, address):
        return struct.unpack('<I', self.u.mem_read(address, 4))[0]

    def ret(self, value=0):
        esp = self.u.reg_read(UC_X86_REG_ESP)
        self.u.reg_write(UC_X86_REG_EAX, value)
        self.u.reg_write(UC_X86_REG_EIP, self.rd(esp))
        self.u.reg_write(UC_X86_REG_ESP, esp + 4)

    def owner(self, address=OWNER, bs=2473, handle=7, flags=0, priority=1):
        self.u.mem_write(address, bytes(0x50))
        self.w(address + 4, handle, bs, 0x7F7F7F7F, priority, 0)
        self.f(address + 0x18, 4)
        self.w(address + 0x30, 0x76543210, CALLBACK)
        self.f(address + 0x38, 1)
        self.w(address + 0x44, -1, flags)
        return address

    def call(self, address, args=(), regs=None, stop=STOP):
        self.w(STACK, stop, *args)
        self.u.reg_write(UC_X86_REG_ESP, STACK)
        for reg, value in (regs or {}).items():
            self.u.reg_write(reg, value)
        self.u.emu_start(address, stop, count=2_000_000)
        if self.u.reg_read(UC_X86_REG_EIP) != stop:
            raise AssertionError(f'call {address:#x} failed to return')

    def event(self, event, owner=OWNER):
        self.call(DISPATCH, regs={UC_X86_REG_ESI: owner, UC_X86_REG_EDX: event,
                                 UC_X86_REG_EAX: CALLBACK, UC_X86_REG_ECX: 0x76543210})

    def update(self, owner=OWNER):
        self.call(0x457030, (owner, 0))

    def end(self, event=4, owner=OWNER):
        self.call(0x4566C0, (event,), {UC_X86_REG_EAX: owner})

    def render(self):
        # Execute the actual HUD CALL instruction; stop before the next HUD call.
        self.call(RENDER_CALL, stop=RENDER_CALL + 5)

    def reset(self):
        self.call(RESET_CALL, stop=RESET_CALL + 5)

    def hook(self, u, address, size, data):
        native_name = {0x63F830: 'nativeCaptionRenderer', 0x611A90: 'nativeTextMeasure',
                       0x611C70: 'nativeWrapEntry', 0x457030: 'nativeSpeechUpdate',
                       0x4566C0: 'nativeSpeechEnd'}.get(address)
        if native_name:
            self.executed[native_name] = self.executed.get(native_name, 0) + 1
        for name, target in self.symbols.items():
            if address == target:
                self.executed[name] = self.executed.get(name, 0) + 1
        esp = u.reg_read(UC_X86_REG_ESP)
        if self.symbols and address == self.symbols['GameplayCaptionLookup']:
            bs = self.rd(esp + 4)
            self.ret(self.text_addresses.get(bs, 0))
            return
        if self.symbols and address in (self.symbols['malloc'], self.symbols['free'], self.symbols['atexit']):
            result = 0
            if address == self.symbols['malloc']:
                size = self.rd(esp + 4)
                result = self.heap_next
                self.heap_next = (self.heap_next + max(size, 1) + 15) & ~15
                if self.heap_next > 0x22000000:
                    raise ValueError('synthetic allocation budget exceeded')
            self.ret(result)
            return
        if address == DISPATCH:
            owner = u.reg_read(UC_X86_REG_ESI)
            self.events.append({'event': u.reg_read(UC_X86_REG_EDX), 'owner': owner,
                                'bs': self.rd(owner + 8), 'handle': self.rd(owner + 4),
                                'flags': self.rd(owner + 0x48)})
        if self.extra_hook and self.extra_hook(address):
            return
        boundary = {0x60D8F0: 'audio_ready', 0x60D930: 'audio_active',
                    0x456B40: 'spatial_range', 0x60DA00: 'audio_volume',
                    0x60D9F0: 'audio_position', 0x60D850: 'audio_stop',
                    0x60C5D0: 'audio_fade_stop', CALLBACK: 'callback',
                    0x7B4610: 'name_copy', 0x613330: 'gpu_text',
                    0x6132E0: 'gpu_text_int', 0x638B40: 'gpu_background',
                    0x40D110: 'gpu_blend'}.get(address)
        if not boundary:
            return
        self.boundaries[boundary] = self.boundaries.get(boundary, 0) + 1
        esp = u.reg_read(UC_X86_REG_ESP)
        result = 0
        if boundary == 'audio_ready':
            result = int(self.audio_ready and 0 < self.rd(esp + 4) < 0x80000000)
        elif boundary == 'audio_active':
            result = int(self.audio_active)
        elif boundary == 'callback':
            self.callbacks.append(list(struct.unpack('<III', u.mem_read(esp + 4, 12))))
        elif boundary == 'name_copy':
            dst, src, count = struct.unpack('<III', u.mem_read(esp + 4, 12))
            value = bytes(u.mem_read(src, count)).split(b'\0', 1)[0]
            u.mem_write(dst, value + bytes(count - len(value)))
            result = dst
        elif boundary == 'gpu_text':
            self.draws.append(list(struct.unpack('<ffIII', u.mem_read(esp + 4, 20))))
        elif boundary == 'gpu_text_int':
            x, y, text, color = struct.unpack('<IIII', u.mem_read(esp + 4, 16))
            payload = bytes(u.mem_read(text, 8192)).split(b'\0', 1)[0]
            style = self.rd(0x9E88AC)
            sx, sy = struct.unpack('<ff', u.mem_read(style + 8, 8))
            self.draws.append({'x': self.rd(x), 'y': self.rd(y), 'payload_hex': payload.hex(),
                               'sx': sx, 'sy': sy, 'color': color})
        elif boundary == 'gpu_blend':
            result = 1
        self.ret(result)


def native_cases(exe):
    rows = []
    for flags in (0, 4):
        r = Replay(exe)
        r.owner(flags=flags)
        r.update()
        r.render()
        rows.append({'case': f'ready_voice_native_flags_{flags}', 'events': r.events,
                     'callbacks': r.callbacks, 'draw_count': len(r.draws),
                     'selected_bs': r.rd(0x9FE868), 'display_gate': r.rd(0x9FE8DC),
                     'pass': [e['event'] for e in r.events] == [2] and not r.draws})
    r = Replay(exe)
    r.owner(flags=4)
    r.update()
    r.update()
    r.f(OWNER + 0x18, -1)
    r.update()  # Audio still active even after estimated duration expires.
    r.audio_active = False
    r.update()  # Real native end path clears owner BS and handle after event 3.
    rows.append({'case': 'duration_expired_until_audio_ends', 'events': r.events,
                 'callbacks': r.callbacks, 'final_bs': r.rd(OWNER + 8),
                 'final_handle': r.rd(OWNER + 4),
                 'pass': [e['event'] for e in r.events] == [2, 2, 2, 3]
                         and r.rd(OWNER + 8) == 0 and r.rd(OWNER + 4) == 0xFFFFFFFF})
    r = Replay(exe)
    r.owner(flags=4)
    r.w(0x8BB378, 0)
    before = bytes(r.u.mem_read(OWNER, 0x50))
    r.update()
    rows.append({'case': 'zero_tick_pauses_speech_updates', 'events': r.events,
                 'pass': not r.events and before == bytes(r.u.mem_read(OWNER, 0x50))})
    r = Replay(exe)
    r.owner(flags=4)
    r.w(OWNER, NODE)
    r.w(NODE, 2508)
    r.w(NODE + 0x10, -1)
    r.w(NODE + 0x1C, CALLBACK, 0x76543210, 0)
    r.call(0x456730, (OWNER,))
    rows.append({'case': 'cancel_queue_then_stop_active', 'events': r.events,
                 'callbacks': r.callbacks, 'pass': [e['event'] for e in r.events] == [5, 4]
                 and r.rd(OWNER) == 0 and r.rd(OWNER + 8) == 0})
    r = Replay(exe)
    r.owner(flags=0)
    r.audio_ready = False
    r.update()
    rows.append({'case': 'active_audio_not_ready_yet', 'events': r.events,
                 'pass': [e['event'] for e in r.events] == [2]
                 and r.rd(0x9FE868) == 0 and r.rd(0x9FE8E0) == 2})
    r = Replay(exe)
    r.owner(flags=0)
    r.update()
    r.reset()
    rows.append({'case': 'native_hud_reset_clears_selection',
                 'pass': r.rd(0x9FE868) == 0 and r.rd(0x9FE8D8) == 0
                         and r.rd(0x8BDBD4) == 1})
    return rows


def compiled_cases(exe, library, map_path, rollback=False, baseline_with_library=False, audit=None):
    rows = []

    def fresh(**kw):
        return Replay(exe, library, map_path, rollback, baseline_with_library=baseline_with_library, **kw)

    def add(name, r, passed, **details):
        if audit is not None and rollback:
            audit.setdefault('restored_copy_checks', []).append(r.rollback_bytes_verified)
        rows.append({'case': name, 'pass': bool(passed), 'events': r.events,
                     'callbacks': r.callbacks, 'draws': r.draws,
                     'executed_hooks': r.executed, **details})

    added = not (rollback or baseline_with_library)

    for flags in (0, 4):
        r = fresh()
        r.owner(flags=flags)
        before_style = bytes(r.u.mem_read(0x8BAB6C, 28))
        r.update()
        r.render()
        restored = r.rd(0x9E88AC) == 0x8BABC0 and r.rd(0x9E88A4) == 24
        good = len(r.draws) == (1 if added else 0) and restored
        if rollback:
            good = good and r.rollback_bytes_verified
        if added:
            good = good and abs(r.draws[0]['sy'] - 3.75) < 0.001 and r.executed.get('wrapHook', 0) > 0
            good = good and r.executed.get('nativeTextMeasure', 0) > 0
        add(f'compiled_ready_voice_flags_{flags}', r, good,
            font_style_restored=restored,
            native_style_unchanged=before_style == bytes(r.u.mem_read(0x8BAB6C, 28)))
    # Compare ABI against the original dispatcher, including the flags feeding
    # its conditional branch and the optional cdecl callback's argument order.
    protected = (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX,
                 UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP, UC_X86_REG_EFLAGS)
    for callback in (0, CALLBACK):
        original = Replay(exe)
        changed = fresh()
        snapshots = []
        for r in (original, changed):
            r.owner(flags=4)
            r.call(DISPATCH, regs={UC_X86_REG_EAX: callback, UC_X86_REG_EBX: 0x12345678,
                   UC_X86_REG_ECX: 0x76543210, UC_X86_REG_EDX: 2, UC_X86_REG_ESI: OWNER,
                   UC_X86_REG_EDI: 0x23456789, UC_X86_REG_EBP: 0x3456789A, UC_X86_REG_EFLAGS: 0x246})
            snapshots.append([r.u.reg_read(reg) for reg in protected])
        add(f'compiled_dispatch_abi_callback_{bool(callback)}', changed,
            snapshots[0] == snapshots[1] and original.callbacks == changed.callbacks,
            baseline_registers=snapshots[0], modified_registers=snapshots[1])
    if not added:
        return rows

    r = fresh()
    r.owner(flags=4)
    r.audio_ready = False
    r.update(); r.render()
    before = len(r.draws)
    r.audio_ready = True
    r.update(); r.update(); r.update(); r.render()
    add('ready_transition_and_repeat_event_deduplication', r, before == 0 and len(r.draws) == 1)

    r = fresh()
    r.owner(flags=4)
    r.update()
    r.f(OWNER + 0x18, -1)
    r.update(); r.render()
    before = len(r.draws)
    r.audio_active = False
    r.update(); r.render()
    add('caption_follows_audio_completion_not_estimated_duration', r,
        before == 1 and len(r.draws) == 1 and [e['event'] for e in r.events] == [2, 2, 3])

    for event in (1, 3, 4):
        r = fresh()
        r.owner(flags=4)
        r.update()
        if event == 1:
            r.event(1)
        else:
            r.end(event)
        r.render()
        add(f'event_{event}_clears_old_cue', r, not r.draws)

    r = fresh()
    r.owner(flags=4)
    r.update()
    for event in (0, 5, 6):
        r.event(event)
    r.render()
    add('queued_cancel_or_refused_request_does_not_kill_active_cue', r, len(r.draws) == 1)

    r = fresh()
    r.owner(flags=4)
    r.update()
    r.w(0x8BB378, 0)
    before = len(r.events)
    r.update()
    still = len(r.events)
    # The production call site is behind the HUD tick gate. Resume before drawing.
    r.w(0x8BB378, 1)
    r.render()
    add('pause_freezes_events_and_keeps_active_cue_for_resume', r, before == still and len(r.draws) == 1)

    r = fresh()
    r.owner(flags=4)
    r.update()
    r.owner(OWNER + 0x100, bs=2508, handle=8, flags=4, priority=2)
    r.update(OWNER + 0x100); r.render()
    r.end(4, OWNER + 0x100); r.render()
    r.end(3, OWNER); r.render()
    add('multiple_speakers_priority_and_live_candidate_resume', r,
        len(r.draws) == 2 and bytes.fromhex(r.draws[0]['payload_hex']) == r.payloads[2508]
        and bytes.fromhex(r.draws[1]['payload_hex']) == r.payloads[2473])

    r = fresh()
    r.owner(flags=4)
    r.update()
    r.w(0x91C88C, 0)
    r.render()
    disabled = len(r.draws)
    r.w(0x91C88C, 1)
    r.render()
    add('subtitle_option_is_respected', r, disabled == 0 and len(r.draws) == 1)

    r = fresh()
    r.owner(flags=4)
    r.update()
    r.w(0xA0A704, 1)
    r.render()
    during_sequence = len(r.draws)
    r.w(0xA0A704, 0)
    r.render()
    add('scripted_sequence_flag_does_not_hide_ready_voice', r, during_sequence == 1 and len(r.draws) == 2)

    r = fresh()
    r.owner(flags=4)
    r.update()
    r.reset(); r.render()
    add('scene_reset_clears_new_and_native_cues', r, not r.draws and r.rd(0x9FE868) == 0
        and r.executed.get('GameplayCaptionResetHook') == 1)

    r = fresh()
    r.w(0x9FE868, 2473)
    r.w(0x9FE8DC, 8)
    r.f(0x9FE8D4, 1)
    r.w(0x8AA130, 0, 0)
    r.render()
    add('native_caption_fallback_is_preserved', r, len(r.draws) == 1
        and r.executed.get('nativeCaptionRenderer') == 1)

    r = fresh()
    r.owner(flags=8)
    r.update(); r.render()
    add('native_same_bs_caption_is_not_drawn_twice', r, len(r.draws) == 1
        and r.rd(0x9FE868) == 2473 and r.rd(0x9FE8DC) == 8
        and not r.executed.get('nativeCaptionRenderer'))

    r = fresh()
    r.owner(flags=4)
    r.update()
    r.u.mem_protect(OWNER, 0x1000, 0)
    r.render()
    add('draw_does_not_dereference_owner_after_event_copy', r, len(r.draws) == 1)

    for bs, handle in ((0, 7), (2510, 7), (2473, -1), (2473, 0)):
        r = fresh()
        r.owner(flags=4, bs=bs, handle=handle)
        r.event(2); r.render()
        add(f'missing_text_or_voice_{bs}_{handle}', r, not r.draws)

    for width, height, glyphs in ((640, 480, 72), (1920, 1080, 72), (2880, 1800, 72), (3840, 2160, 360)):
        r = fresh(glyphs=glyphs)
        r.w(0x872500, width, height)
        r.owner(flags=4)
        r.update(); r.render()
        good = len(r.draws) == 1
        if good:
            draw = r.draws[0]
            payload = bytes.fromhex(draw['payload_hex'])
            lines = payload.split(b'\n')
            measured_width = max(line.count(b'\x1f') for line in lines) * 13.92 * draw['sx']
            measured_height = len(lines) * 16 * draw['sy']
            good = payload.replace(b'\n', b'') == r.payloads[2473]
            good = good and draw['x'] > 0 and draw['x'] + measured_width <= width
            good = good and draw['y'] > 0 and draw['y'] + measured_height <= height
        add(f'compiled_wrapping_and_layout_{width}x{height}_{glyphs}', r, good)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--library', type=Path)
    parser.add_argument('--map', type=Path)
    parser.add_argument('--rollback', action='store_true')
    parser.add_argument('--baseline-with-library', action='store_true')
    parser.add_argument('--require-added-captions', action='store_true',
                        help='Negative control: fail if native silent-caption cases still draw zero')
    args = parser.parse_args()
    if (args.map or args.rollback or args.baseline_with_library) and not args.library:
        parser.error('--map/--rollback require --library')
    if args.rollback and args.baseline_with_library:
        parser.error('--rollback and --baseline-with-library are mutually exclusive')
    rows = native_cases(args.exe)
    audit = {}
    compiled = compiled_cases(args.exe, args.library, args.map, args.rollback, args.baseline_with_library, audit) if args.library else []
    rows += compiled
    passed = all(row['pass'] for row in rows)
    if args.require_added_captions:
        passed = passed and bool(args.library and not (args.rollback or args.baseline_with_library)) and all(
            len(row['draws']) > 0 for row in compiled if row['case'].startswith('compiled_ready_voice'))
    result = {'kind': 'offline native x86 speech lifecycle replay', 'game_launched': False,
              'in_game_verified': False, 'input_sha256': EXPECTED,
              'library_sha256': hashlib.sha256(args.library.read_bytes()).hexdigest() if args.library else None,
              'map_sha256': hashlib.sha256(args.map.read_bytes()).hexdigest() if args.map else None,
              'rollback': args.rollback,
              'baseline_with_library': args.baseline_with_library,
              'rollback_byte_verification': audit,
              'controlled_boundaries': ['audio-device ready/active status', 'spatial volume/range',
                                        'GPU text submission', 'synthetic owner/BS table',
                                        'compiled GameplayCaptionLookup return only (locale input)',
                                        'malloc/free/atexit and x86 SEH/TEB resource boundaries'],
              'patch_signatures': {hex(k): v.hex() for k, v in SIGNATURES.items()},
              'passed': passed, 'cases': rows}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(('PASS' if passed else 'FAIL') + f': native lifecycle {sum(row["pass"] for row in rows)}/{len(rows)}; native silent-caption draw counts=' + ','.join(str(row['draw_count']) for row in rows if 'draw_count' in row)
          + ('; compiled added-caption draw counts=' + ','.join(str(len(row['draws'])) for row in compiled if row['case'].startswith('compiled_ready_voice')) if compiled else ''))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
