"""Read-only, hash-bound inspection of Second Sight's dormant glyph renderer.

This tool reads PE bytes; it never opens a game process or writes the input.
Run with --self-test for the inspector's synthetic grammar/patch-site tests.
The profile describes one executable, not an engine-wide address guarantee.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys


EXPECTED_SHA256 = "4092a8d1fb042dffe9fb95e2185f32cb80390299145e8d453a5e909a06d35fda"
EXPECTED_SIZE = 5_484_544
MARKER_SITES = (0x610A96, 0x6119F3, 0x611A59, 0x611D1B, 0x611D58, 0x612561)
PROTECTED_ENTRIES = (0x612BC0, 0x613330)
PATCH_SITES = {
    "cutscene_subtitle_style": (0x543031, "e85ad50c00"),
    "cutscene_subtitle_restore": (0x5431E8, "d905b4749600"),
    "text_batch_begin": (0x610EFD, "e8cecfdfff"),
    "text_batch_end_tail": (0x610FA8, "e953d1dfff"),
    "text_page_bind": (0x6125C1, "e85ad6dfff"),
    "text_latin_bind": (0x612677, "e8a4d5dfff"),
    "terminal_compose_esi_call": (0x5D0643, "e838ffffff"),
    "terminal_compose_edi_call": (0x5D06FB, "e880feffff"),
    "localized_wrap_entry": (0x611C70, "81ec04020000"),
    "atlas_signed_page_mask": (0x612595, "81e2ff000000"),
    "atlas_page_shift": (0x6125A7, "c1fe08"),
    "atlas_column_mask": (0x6125CF, "81e10f000080"),
    "atlas_signed_column_correction": (0x6125D8, "83c9f0"),
    "atlas_page_multiplier": (0x6125DC, "c1e608"),
    "atlas_row_division_adjustment": (0x6125E4, "83e20f"),
    "atlas_row_shift": (0x6125FC, "c1f804"),
    "bs_after_relocation_call": (0x43E663, "e818201000"),
    "font_mode_reset_call": (0x611885, "e866ebffff"),
    "resource_size_entry": (0x49DDF0, "a1d00f9100"),
    "resource_read_entry": (0x49E4E0, "a1d00f9100"),
    "glyph_count_entry": (0x6119D0, "51a1a0889e00"),
    "glyph_substring_entry": (0x611A30, "51a1a0889e00"),
    "localized_key_expansion": (0x610260, "538b5c2408"),
    "pda_token_word_call": (0x58074D, "e80effffff"),
    "pda_token_skip_call": (0x580832, "e8d9fdffff"),
    "pda_link_expand_call": (0x580C2A, "e811faffff"),
    "pda_plain_expand_call": (0x580C4C, "e8eff9ffff"),
}

# Ranges start on independently observed instruction boundaries. Jump tables
# are deliberately excluded: disassembling them as code invents instructions.
RANGES = {
    "mode_setter": (0x6103F0, 0x610400),
    "font_eligibility": (0x610460, 0x6104C0),
    "font_enqueue": (0x610510, 0x61056B),
    "font_select": (0x610590, 0x6105D5),
    "decimal_parser": (0x610680, 0x6106DC),
    "measure_setup": (0x6106E0, 0x61082D),
    "measure_glyph": (0x610A80, 0x610B09),
    "font_resolve": (0x611840, 0x61188D),
    "glyph_count_and_substring": (0x6119D0, 0x611A87),
    "word_wrap_glyph": (0x611CF0, 0x611E1B),
    "draw_setup": (0x611F70, 0x6120A5),
    "draw_glyph": (0x612538, 0x61265B),
    "bs_relocation": (0x43E650, 0x43E683),
    "bs_key_name_cache": (0x540680, 0x5407E8),
    "resource_size": (0x49DDF0, 0x49DE2D),
    "resource_sort_key": (0x49E490, 0x49E4C5),
    "resource_read": (0x49E4E0, 0x49E578),
    "resource_read_return": (0x49EB2B, 0x49EB6B),
    "ui_255byte_copy": (0x4BEAA0, 0x4BEAE4),
    "texture_enqueue": (0x4A0130, 0x4A019C),
    "texture_queue_dispatch": (0x49FA5C, 0x49FAB8),
    "texture_load": (0x413A60, 0x413B62),
}


def native_decimal_token(data: bytes, position: int = 0) -> tuple[int, int]:
    """Model 0x610680: skip marker, consume *all* digits, retain last four.

    The returned position is the first non-digit. Native callers implement this
    as a digit-count increment of their cursor plus their own marker increment.
    This function is a static model, not an emulator or runtime test.
    """
    cursor = position + 1
    result = 0
    while cursor < len(data) and 48 <= data[cursor] <= 57:
        result = (result * 10 + data[cursor] - 48) % 10000
        cursor += 1
    return result, cursor


def validate_encoded(data: bytes, marker: int = 0x1F) -> list[int]:
    """Validate the POC's strict all-visible-glyph token subset.

    NUL is omitted from the supplied body. Native control blocks must be
    validated separately, not flattened through this restricted function.
    """
    glyphs: list[int] = []
    cursor = 0
    while cursor < len(data):
        if data[cursor] in (9, 10, 32):
            cursor += 1
            continue
        if data[cursor] != marker:
            raise ValueError(f"unexpected visible/control byte at {cursor}")
        digits = data[cursor + 1:cursor + 5]
        if len(digits) != 4 or not all(48 <= value <= 57 for value in digits):
            raise ValueError(f"expected four decimal digits at {cursor}")
        glyph, end = native_decimal_token(data, cursor)
        if end != cursor + 5:
            raise ValueError(f"greedy decimal suffix at {cursor}")
        if glyph >= 6 * 1024:
            raise ValueError(f"glyph outside six declared pages: {glyph}")
        glyphs.append(glyph)
        cursor = end
    return glyphs


def self_test() -> None:
    cases = (
        (b",0001\0", (1, 5)),
        (b",00015\0", (15, 6)),
        (b",12345x", (2345, 6)),
        (b",x", (0, 1)),
        (b"\x1f6143\x1f0001", (6143, 5)),
    )
    for source, expected in cases:
        if native_decimal_token(source) != expected:
            raise AssertionError((source, expected))
    if validate_encoded(b"\x1f0001 \x1f6143\n\x1f0002") != [1, 6143, 2]:
        raise AssertionError("valid token sequence rejected")
    rejected = (b"\x1f00015", b"\x1f6144", b"\x1f000", b"\x1f000A", b"\x1e", b"A", b"\0")
    for source in rejected:
        try:
            validate_encoded(source)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid input accepted: {source!r}")
    occupied: set[int] = set()
    sites = list(PATCH_SITES.values()) + [(site, "3c2c") for site in MARKER_SITES]
    sites += [(0x8BA864 + page * 32, "9f000000") for page in range(6)]
    for address, expected in sites:
        span = set(range(address, address + len(bytes.fromhex(expected))))
        if occupied & span:
            raise AssertionError("patch-site overlap")
        if any(entry in span for entry in PROTECTED_ENTRIES):
            raise AssertionError("FusionFix entry overlap")
        occupied.update(span)
    print("SELF_TEST PASS: 5 parser cases, 1 valid encoding, 7 rejected encodings, disjoint patch sites")


def inspect(executable: Path, with_disassembly: bool) -> dict:
    import pefile

    data = executable.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != EXPECTED_SHA256 or len(data) != EXPECTED_SIZE:
        raise ValueError(f"unsupported executable identity: sha256={digest}, size={len(data)}")
    pe = pefile.PE(data=data)
    image_base = pe.OPTIONAL_HEADER.ImageBase

    def read(va: int, size: int) -> bytes:
        offset = pe.get_offset_from_rva(va - image_base)
        result = data[offset:offset + size]
        if len(result) != size:
            raise ValueError(f"short mapped read at 0x{va:08X}")
        return result

    def string(va: int) -> str:
        offset = pe.get_offset_from_rva(va - image_base)
        return data[offset:data.index(0, offset)].decode("ascii")

    descriptors = []
    for index in range(10):
        va = 0x8BA7E0 + index * 32
        words = struct.unpack("<8I", read(va, 32))
        descriptors.append({
            "index": index, "va": f"0x{va:08X}", "path": string(words[0]),
            "flags": f"0x{words[1]:08X}", "glyph_metrics_va": f"0x{words[2]:08X}",
            "spacing_table_va": f"0x{words[3]:08X}", "height": words[4],
            "advance": words[5], "spacing_adjustment": words[6],
            "texture_handle_initial": f"0x{words[7]:08X}",
        })
    sites = []
    all_sites = dict(PATCH_SITES)
    all_sites.update({f"marker_{n}": (va, "3c2c") for n, va in enumerate(MARKER_SITES)})
    all_sites.update({f"page_{n}_flags": (0x8BA864 + n * 32, "9f000000") for n in range(6)})
    for name, (va, expected) in all_sites.items():
        actual = read(va, len(bytes.fromhex(expected))).hex()
        if actual != expected:
            raise ValueError(f"profile mismatch at {name}: {actual} != {expected}")
        sites.append({"name": name, "va": f"0x{va:08X}", "expected_hex": actual})
    result = {
        "evidence": "verified static PE bytes; execution and visual acceptance unobserved",
        "input": str(executable.resolve()), "sha256": digest, "size": len(data),
        "image_base": f"0x{image_base:08X}", "machine": f"0x{pe.FILE_HEADER.Machine:04X}",
        "pefile_version": pefile.__version__, "descriptors": descriptors,
        "glyph_relative_scale": struct.unpack("<f", read(0x7DE438, 4))[0],
        "patch_site_preconditions": sites,
        "protected_fusionfix_entries": [f"0x{address:08X}" for address in PROTECTED_ENTRIES],
        "marker_1f_measure_dispatch_target": f"0x{struct.unpack('<I', read(0x610C68 + read(0x610C7C + 0x1F - 9, 1)[0] * 4, 4))[0]:08X}",
        "runtime_status": "not executed",
    }
    if with_disassembly:
        import capstone
        cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        result["capstone_version"] = capstone.__version__
        result["disassembly"] = {
            name: [f"{i.address:08X} {i.bytes.hex():24s} {i.mnemonic} {i.op_str}".rstrip()
                   for i in cs.disasm(read(start, end - start), start)]
            for name, (start, end) in RANGES.items()
        }
    if hashlib.sha256(executable.read_bytes()).hexdigest() != digest:
        raise ValueError("input changed during inspection")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path, nargs="?")
    parser.add_argument("--output", type=Path, help="write a JSON report; never writes the executable")
    parser.add_argument("--disassemble", action="store_true", help="include focused Capstone evidence")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        if args.executable is None:
            if args.self_test:
                return 0
            parser.error("executable is required unless --self-test is used")
        if args.output is not None:
            same_path = args.output.resolve() == args.executable.resolve()
            same_file = args.output.exists() and args.output.samefile(args.executable)
            if same_path or same_file:
                raise ValueError("report path must differ from executable")
        report = inspect(args.executable, args.disassemble)
        encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded, encoding="utf-8")
            # Reopen the generated evidence so write failure is not silent.
            if json.loads(args.output.read_text(encoding="utf-8")) != report:
                raise ValueError("report round-trip mismatch")
        else:
            print(encoded, end="")
        print("RESULT static renderer inspection PASS; original SHA256 unchanged; game not executed")
        return 0
    except (ValueError, OSError, ImportError) as error:
        print(f"ERROR {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
