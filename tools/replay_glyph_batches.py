"""Offline x86 replay of the native text callback and compiled batch hooks.

No process is launched or attached. The hash-bound user EXE supplies instructions
to Unicorn; primitive submission and texture storage are synthetic boundaries.
Modified mode executes the compiled ASI hooks, not a Python copy of their policy.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import struct

EXE_SHA256 = "4092a8d1fb042dffe9fb95e2185f32cb80390299145e8d453a5e909a06d35fda"
EXE_SIZE = 5484544
SLOTS_PER_PAGE = 1024
PAGE_COUNT = 6
CALLBACK = 0x610E60
COUNT_CALLBACK = 0x610D10
BEGIN = 0x40DED0
EMIT = 0x60FEC0
END = 0x40E100
BIND = 0x40FC20
BIND_STORAGE = 0x40DB70
REMAINING = 0x9E88B8
PENDING = 0x9E88BC
CURSOR = 0x8DAF00
ACTUAL = 0x8DAF14
TEXTURE = 0x8DA4D0
RECORDING = 0x8DAF6C
PAGE_TEXTURE = 0x100
LATIN_TEXTURE = 0x200
STACK_BASE = 0x20000000
STACK_SIZE = 0x00100000
STACK_TOP = STACK_BASE + STACK_SIZE - 0x1000
STOP = STACK_BASE + 0x100
COLOR_VALUE = STACK_BASE + 0x200
COLOR_POINTER = STACK_BASE + 0x204
VERTICES = STACK_BASE + 0x1000

PATCH_SITES = {
    "begin": (0x610EFD, bytes.fromhex("E8 CE CF DF FF"), "call"),
    "end": (0x610FA8, bytes.fromhex("E9 53 D1 DF FF"), "jmp"),
    "page_bind": (0x6125C1, bytes.fromhex("E8 5A D6 DF FF"), "call"),
    "latin_bind": (0x612677, bytes.fromhex("E8 A4 D5 DF FF"), "call"),
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_executable(data: bytes) -> None:
    if len(data) != EXE_SIZE or sha256(data) != EXE_SHA256:
        raise ValueError("unsupported executable identity")


@lru_cache(maxsize=3)
def pe_image(data: bytes) -> tuple[int, int, bytes]:
    """Cache PE parsing only; every replay still gets independent machine memory."""
    import pefile
    pe = pefile.PE(data=data, fast_load=True)
    if pe.FILE_HEADER.Machine != 0x14C:
        raise ValueError("input PE must be x86")
    return (pe.OPTIONAL_HEADER.ImageBase, (pe.OPTIONAL_HEADER.SizeOfImage + 4095) & ~4095,
            pe.get_memory_mapped_image())


def load_glyphs(path: Path) -> dict[str, int]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("executable_sha256") != EXE_SHA256:
        raise ValueError("manifest executable identity differs")
    glyphs = manifest.get("glyphs")
    if not isinstance(glyphs, dict) or not glyphs:
        raise ValueError("manifest has no glyph mapping")
    if any(not isinstance(char, str) or len(char) != 1 or type(slot) is not int
           or slot < 0 or slot >= PAGE_COUNT * SLOTS_PER_PAGE
           for char, slot in glyphs.items()):
        raise ValueError("invalid glyph mapping")
    if len(set(glyphs.values())) != len(glyphs):
        raise ValueError("duplicate glyph slots")
    return glyphs


def map_symbol(text: str, name: str) -> int:
    """Resolve a unique MSVC MAP symbol using its preferred-base VA column."""
    matches = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 3 or not re.fullmatch(r"[0-9A-Fa-f]{4}:[0-9A-Fa-f]{8}", fields[0]):
            continue
        if name not in fields[1]:
            continue
        if re.fullmatch(r"[0-9A-Fa-f]{8,16}", fields[2]):
            matches.append(int(fields[2], 16))
    if len(set(matches)) != 1:
        raise ValueError(f"MAP symbol must resolve uniquely: {name}")
    return matches[0]


@dataclass(frozen=True)
class Token:
    label: str
    slot: int = 0
    latin: bool = False
    space: bool = False
    clipped: bool = False

    @property
    def texture(self) -> int:
        return LATIN_TEXTURE if self.latin or self.space else PAGE_TEXTURE + self.slot // SLOTS_PER_PAGE

    @property
    def cell(self) -> int:
        return self.slot % SLOTS_PER_PAGE


class NativeReplay:
    """Execute the original callback, count pass, and actual compiled shims."""

    def __init__(self, exe: Path, asi: Path | None = None, map_path: Path | None = None,
                 symbols: dict[str, str] | None = None):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
        from unicorn import x86_const
        self.reg = x86_const
        exe_data = exe.read_bytes()
        validate_executable(exe_data)
        self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        self.exe_hash = sha256(exe_data)
        self.asi_hash = None
        self.symbols: dict[str, int] = {}
        self.executed_hooks: dict[str, int] = {}
        self._map_pe(exe_data)
        self.uc.mem_map(STACK_BASE, STACK_SIZE)
        self.write_u32(0x872500, 1920)
        self.write_u32(0x872504, 1080)
        self.write_u32(COLOR_VALUE, 0xFFFFFFFF)
        self.write_u32(COLOR_POINTER, COLOR_VALUE)
        self.write_u32(RECORDING, 0)
        self.write_u32(TEXTURE, PAGE_TEXTURE)
        if asi is not None:
            if map_path is None or symbols is None:
                raise ValueError("modified replay needs ASI, MAP, and hook symbols")
            asi_data = asi.read_bytes()
            self.asi_hash = sha256(asi_data)
            self._map_pe(asi_data)
            text = map_path.read_text(encoding="utf-8", errors="replace")
            self.symbols = {key: map_symbol(text, name) for key, name in symbols.items()}
            module_base, module_size, _ = pe_image(asi_data)
            if any(not module_base <= target < module_base + module_size for target in self.symbols.values()):
                raise ValueError("MAP hook is outside the supplied ASI image")
            for key, (address, expected, kind) in PATCH_SITES.items():
                if bytes(self.uc.mem_read(address, 5)) != expected:
                    raise ValueError(f"native patch signature mismatch: {address:#x}")
                target = self.symbols["bind" if key.endswith("bind") else key]
                opcode = b"\xe8" if kind == "call" else b"\xe9"
                self.uc.mem_write(address, opcode + struct.pack("<i", target - address - 5))
        self.current_token: Token | None = None
        self.current_index = 0
        self.queue: list[dict] = []
        self.submissions: list[dict] = []
        self.begin_count = self.end_count = self.bind_count = 0
        self.capacity = 0
        self.uc.hook_add(UC_HOOK_CODE, self._code)

    def _map_pe(self, data: bytes) -> None:
        base, size, image = pe_image(data)
        self.uc.mem_map(base, size)
        self.uc.mem_write(base, image)

    def read_u32(self, address: int) -> int:
        return struct.unpack("<I", self.uc.mem_read(address, 4))[0]

    def write_u32(self, address: int, value: int) -> None:
        self.uc.mem_write(address, struct.pack("<I", value & 0xFFFFFFFF))

    def _args(self, count: int) -> tuple[int, ...]:
        esp = self.uc.reg_read(self.reg.UC_X86_REG_ESP)
        return struct.unpack(f"<{count}I", self.uc.mem_read(esp + 4, count * 4))

    def _return(self, value: int = 0) -> None:
        esp = self.uc.reg_read(self.reg.UC_X86_REG_ESP)
        self.uc.reg_write(self.reg.UC_X86_REG_EAX, value)
        self.uc.reg_write(self.reg.UC_X86_REG_ESP, esp + 4)
        self.uc.reg_write(self.reg.UC_X86_REG_EIP, self.read_u32(esp))

    def _code(self, uc, address, size, user_data) -> None:
        for name, target in self.symbols.items():
            if address == target:
                self.executed_hooks[name] = self.executed_hooks.get(name, 0) + 1
        if address == BEGIN:
            fmt, mode, count, texture = self._args(4)
            if fmt != 0x92 or mode != 2 or count % 4 or texture != 0xFFFFFFF6:
                raise ValueError("unexpected native text Begin arguments")
            if self.queue:
                raise ValueError("Begin would discard unsubmitted glyphs")
            self.capacity = count // 4 * 6
            self.write_u32(ACTUAL, 0)
            self.write_u32(0x8DAFA4, 5)
            self.write_u32(0x8DAFA8, fmt)
            self.write_u32(0x8DAFAC, mode)
            self.write_u32(0x8DAFB0, self.capacity)
            if self.read_u32(RECORDING) == 0:
                self.write_u32(CURSOR, VERTICES)
            self.begin_count += 1
            self._return(1)
        elif address == EMIT:
            if self.current_token is None:
                raise ValueError("glyph emission outside a fixture token")
            args = self._args(16)
            u, v = args[2] & 0xFFFF, args[3] & 0xFFFF
            cell = (v // 256) * 32 + u // 256
            if cell != self.current_token.cell:
                raise ValueError("native callback changed the supplied UV cell")
            self.queue.append(dict(index=self.current_index, cell=cell,
                                   expected_texture=self.current_token.texture,
                                   label=self.current_token.label))
            actual = self.read_u32(ACTUAL) + 6
            if actual > self.capacity:
                raise ValueError("native glyph batch exceeded allocated capacity")
            self.write_u32(ACTUAL, actual)
            self.write_u32(CURSOR, VERTICES + actual * 28)
            self._return()
        elif address == END:
            actual = self.read_u32(ACTUAL)
            if actual != len(self.queue) * 6:
                raise ValueError("native actual-vertex counter differs from emitted quads")
            self.submissions.append(dict(texture=self.read_u32(TEXTURE),
                                         vertices=actual, capacity=self.capacity,
                                         glyphs=list(self.queue)))
            self.queue.clear()
            if self.read_u32(RECORDING) == 0:
                self.write_u32(CURSOR, 0)
            # Native End deliberately leaves ACTUAL stale; Begin resets it.
            self.end_count += 1
            self._return()
        elif address == BIND_STORAGE:
            stage, texture = self._args(2)
            if stage != 0:
                raise ValueError("unexpected texture stage")
            self.write_u32(TEXTURE, texture)
            self.bind_count += 1
            self._return()

    def invoke(self, address: int, args: list[int]) -> None:
        esp = STACK_TOP - (len(args) + 1) * 4
        self.uc.mem_write(esp, struct.pack(f"<{len(args) + 1}I", STOP, *args))
        self.uc.reg_write(self.reg.UC_X86_REG_ESP, esp)
        self.uc.emu_start(address, STOP, count=100000)
        if self.uc.reg_read(self.reg.UC_X86_REG_EIP) != STOP:
            raise ValueError("instruction budget exhausted")
        if self.uc.reg_read(self.reg.UC_X86_REG_ESP) != esp + 4:
            raise ValueError("native cdecl stack imbalance")

    def bind_at_callsite(self, texture: int, latin: bool) -> None:
        site = PATCH_SITES["latin_bind" if latin else "page_bind"][0]
        esp = STACK_TOP - 4
        self.write_u32(esp, texture)
        self.uc.reg_write(self.reg.UC_X86_REG_ESP, esp)
        self.uc.emu_start(site, site + 5, count=100000)
        if self.uc.reg_read(self.reg.UC_X86_REG_EIP) != site + 5:
            raise ValueError("texture hook instruction budget exhausted")
        if self.uc.reg_read(self.reg.UC_X86_REG_ESP) != esp:
            raise ValueError("texture callsite stack imbalance")

    def glyph(self, callback: int, token: Token, index: int, shadow: bool = False) -> None:
        self.current_token, self.current_index = token, index
        x = 1930.0 if token.clipped else 20.0 + index * 18
        floats = [x, 20.0, x + 16, 36.0]
        values = [struct.unpack("<I", struct.pack("<f", v))[0] for v in floats]
        u, v = (token.cell % 32) * 256, (token.cell // 32) * 256
        self.invoke(callback, values + [u, v, u + 248, v + 256, COLOR_POINTER, int(shadow)])

    def replay(self, tokens: list[Token], reverse: dict[int, str], *, shadows: bool = False,
               recording: bool = False) -> dict:
        # Keep emulated ASI globals between calls so consecutive text passes can
        # detect a leaked active-batch flag; reset reporting counters only.
        if self.queue:
            raise ValueError("previous text pass still owns queued vertices")
        self.submissions.clear()
        self.begin_count = self.end_count = 0
        self.write_u32(REMAINING, 0)
        self.uc.mem_write(PENDING, b"\0")
        self.write_u32(RECORDING, int(recording))
        if recording:
            self.write_u32(CURSOR, VERTICES)
        prepass_batches = 0
        for phase, callback in (("count", COUNT_CALLBACK), ("render", CALLBACK)):
            self.invoke(BIND, [PAGE_TEXTURE])
            bound = PAGE_TEXTURE
            for index, token in enumerate(tokens):
                if token.texture != bound:
                    self.bind_at_callsite(token.texture, token.latin or token.space)
                    bound = token.texture
                if token.space:
                    continue
                if shadows:
                    self.glyph(callback, token, index, True)
                self.glyph(callback, token, index)
            if phase == "count":
                prepass_batches = len(self.submissions)
                self.submissions.clear()
                self.begin_count = self.end_count = 0
                if self.read_u32(REMAINING) != sum(not t.space and not t.clipped for t in tokens):
                    raise ValueError("native count pass differs from visible glyph count")
        if self.queue or self.read_u32(REMAINING) != 0:
            raise ValueError("native text pass left an unfinished batch or count")
        rendered: dict[int, str] = {}
        wrong = []
        for batch in self.submissions:
            for glyph in batch["glyphs"]:
                texture = batch["texture"]
                if texture == glyph["expected_texture"]:
                    label = glyph["label"]
                elif PAGE_TEXTURE <= texture < PAGE_TEXTURE + PAGE_COUNT:
                    slot = (texture - PAGE_TEXTURE) * SLOTS_PER_PAGE + glyph["cell"]
                    label = reverse.get(slot, f"<glyph:{slot}>")
                else:
                    label = f"<latin:{glyph['cell']}>"
                rendered[glyph["index"]] = label
                if texture != glyph["expected_texture"]:
                    wrong.append(glyph["index"])
        expected = "".join(t.label for t in tokens if not t.clipped)
        output = "".join(t.label if t.space else rendered.get(i, "")
                         for i, t in enumerate(tokens) if not t.clipped)
        return dict(expected=expected, actual=output, passed=not wrong and output == expected,
                    wrong_indices=wrong, batches=self.end_count, begins=self.begin_count,
                    prepass_shadow_batches=prepass_batches, remaining=self.read_u32(REMAINING),
                    actual_vertices=self.read_u32(ACTUAL), cursor=self.read_u32(CURSOR),
                    pending=int.from_bytes(self.uc.mem_read(PENDING, 1)),
                    executed_hooks=dict(self.executed_hooks))


def fixture_cases(glyphs: dict[str, int], feedback: list[dict]) -> list[tuple[str, list[Token], dict[int, str], bool]]:
    reverse = {slot: char for char, slot in glyphs.items()}
    cases = [(row["name"], [Token(c, glyphs[c]) for c in row["expected"]], reverse, False)
             for row in feedback]
    synthetic = {page * 1024: f"p{page}" for page in range(6)}
    cases.extend([
        ("six-page-alternation", [Token(f"p{p}", p * 1024) for p in (0, 1, 2, 3, 4, 5, 0)], synthetic, False),
        ("plain-latin", [Token(c, ord(c), latin=True) for c in "ABC123"], reverse, False),
        ("latin-space-switch", [Token("p0", 0), Token(" ", space=True), Token("A", 65, latin=True), Token("p1", 1024), Token(" ", space=True)], synthetic, False),
        ("clipped-switch", [Token("p0", 0), Token("hidden", 2048, clipped=True), Token("p1", 1024)], synthetic, False),
        ("shadow-prepass-guard", [Token("p0", 0), Token("p1", 1024), Token("p0", 0)], synthetic, True),
        ("empty-visible-pass", [Token("hidden", 2048, clipped=True), Token(" ", space=True)], synthetic, True),
    ])
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--mode", choices=("baseline", "modified"), required=True)
    parser.add_argument("--feedback", type=Path,
                        default=Path(__file__).resolve().parents[1] / "tests/fixtures/glyph_batch_feedback.json")
    parser.add_argument("--asi", type=Path)
    parser.add_argument("--map", type=Path)
    parser.add_argument("--begin-symbol", default="BeginTextBatchHook")
    parser.add_argument("--end-symbol", default="EndTextBatchHook")
    parser.add_argument("--bind-symbol", default="BindTextTextureHook")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.mode == "modified" and (not args.asi or not args.map):
        parser.error("modified mode requires --asi and --map")
    try:
        glyphs = load_glyphs(args.manifest)
        feedback = json.loads(args.feedback.read_text(encoding="utf-8"))["cases"]
        symbols = dict(begin=args.begin_symbol, end=args.end_symbol, bind=args.bind_symbol)
        results = []
        for name, tokens, reverse, shadows in fixture_cases(glyphs, feedback):
            replay = NativeReplay(args.exe, args.asi if args.mode == "modified" else None,
                                  args.map, symbols)
            results.append(dict(name=name, **replay.replay(tokens, reverse, shadows=shadows)))
        replay = NativeReplay(args.exe, args.asi if args.mode == "modified" else None, args.map, symbols)
        guard = replay.replay([Token("p0", 0), Token("p1", 1024)], {0: "p0", 1024: "p1"}, recording=True)
        guard["glyph_mapping_matches"] = guard.pop("passed")
        guard["passed"] = guard["batches"] == 1 and guard["begins"] == 1 and guard["remaining"] == 0
        guard["assertion"] = "recording mode remains a single original batch; glyph rendering is not asserted"
        results.append(dict(name="recording-mode-unchanged", **guard))
        replay = NativeReplay(args.exe, args.asi if args.mode == "modified" else None, args.map, symbols)
        first = replay.replay([Token("p0", 0), Token("p1", 1024)], {0: "p0", 1024: "p1"})
        second = replay.replay([Token("p1", 1024), Token("p0", 0)], {0: "p0", 1024: "p1"})
        second["passed"] = first["passed"] and second["passed"]
        results.append(dict(name="consecutive-text-pass", **second))
        report = dict(schema=1, mode=args.mode, engine="Unicorn original x86 callback",
                      compiled_asi_hooks_executed=args.mode == "modified",
                      scope="Native count/clipping/batch callbacks; driver supplies page and UV from glyph IDs; GPU rasterization is mocked",
                      executable_sha256=replay.exe_hash, asi_sha256=replay.asi_hash,
                      manifest_sha256=sha256(args.manifest.read_bytes()),
                      map_sha256=sha256(args.map.read_bytes()) if args.mode == "modified" else None,
                      compiled_hook_addresses={key: hex(value) for key, value in replay.symbols.items()},
                      mocked_boundaries=[hex(v) for v in (BEGIN, EMIT, END, BIND_STORAGE)],
                      baseline_reproduces_feedback=(all(results[i]["actual"] == row["observed_baseline"]
                                                        for i, row in enumerate(feedback))
                                                    if args.mode == "baseline" else None),
                      game_started=False, in_game_verified=False,
                      passed=all(r["passed"] for r in results), cases=results)
        code = 0 if report["passed"] else 2
    except Exception as exc:
        # Unicorn/PE loader failures also produce a machine-readable exit-2 result.
        report = dict(schema=1, mode=args.mode, passed=False, error=str(exc),
                      error_type=type(exc).__name__, game_started=False)
        code = 2
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
    print(output, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
