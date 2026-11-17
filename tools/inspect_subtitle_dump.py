"""Inspect subtitle fields in an explicitly supplied recorded minidump.

Never acquires a dump, attaches to a process, launches a game, or treats a
historical snapshot as a diagnosis of the user's current runtime.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path, PureWindowsPath
import re
import struct

from inspect_dialogue_routes import EXE_SHA256, SITES
from minidump_reader import Minidump


IMAGE_BASE = 0x400000
IMAGE_SIZE = 0x457F000
IMAGE_TIMESTAMP = 0x418510AF
KNOWN_006_DUMP = 'd8d542b1331ce2469530a45040a38daa7186417661bc2691d6ddb4571ef04e3c'
FIELDS = (
    ('mode', 0x9649E8, 'I', 'Recorded voice-to-caption mode; this snapshot does not identify the current user scene'),
    ('subtitles_option', 0x91C88C, 'I', 'Recorded subtitle option gate; no current-setting inference'),
    ('hud', 0x8AA0E8, 'I', 'Recorded HUD gate; separate from subtitle text availability'),
    ('active_bs_id', 0x9FE868, 'I', 'Recorded active BS identifier; zero is not evidence that dialogue lacks text'),
    ('display_gate', 0x9FE8DC, 'I', 'Recorded subtitle display gate; not a screenshot or visibility test'),
    ('owner_pointer', 0x9FE8D8, 'I', 'Recorded x86 owner pointer; only explicitly captured memory is read'),
    ('tick', 0x8BB378, 'I', 'Recorded tick value; one sample does not establish progression'),
    ('state', 0xA2BD34, 'I', 'Recorded subtitle-related state; not a root-cause classification'),
    ('priority', 0x8BDBD4, 'I', 'Recorded priority field; no timing or arbitration conclusion'),
    ('fade', 0x9FE8D4, 'f', 'Recorded float fade value; no rendering conclusion'),
)


def unknown(address: int, reason: str, description: str = '') -> dict:
    return dict(address=f'0x{address:08X}', status='unknown', value=None,
                reason=reason, description=description)


def read_field(dump: Minidump, address: int, fmt: str, description: str = '') -> dict:
    if address < 0 or address + 4 > 0x100000000:
        return unknown(address, 'outside x86 address range', description)
    try:
        raw = dump.read(address, 4)
        value = struct.unpack('<' + fmt, raw)[0]
        if fmt == 'f' and not math.isfinite(value):
            return dict(unknown(address, 'non-finite recorded float', description), raw_hex=raw.hex())
        return dict(address=f'0x{address:08X}', status='recorded', value=value,
                    raw_hex=raw.hex(), description=description)
    except (ValueError, struct.error) as error:
        return unknown(address, str(error), description)


def identify_image(dump: Minidump) -> dict:
    matches = [m for m in dump.modules if PureWindowsPath(m['name']).name.lower() == 'secondsight.exe']
    # Windows may record exactly identical module rows twice.
    unique = {tuple(m[k] for k in ('name', 'base', 'size', 'timestamp')): m for m in matches}
    result = dict(status='unknown', recorded_matches=len(matches), unique_matches=len(unique),
                  module=None, header=None, fingerprints=[],
                  reference_executable_sha256=EXE_SHA256,
                  reference_hash_is_recorded_file_hash=False)
    if len(unique) != 1:
        result['reason'] = 'missing or ambiguous main secondsight.EXE module'
        return result
    module = next(iter(unique.values()))
    result['module'] = module
    if module['base'] != IMAGE_BASE or module['size'] != IMAGE_SIZE or module['timestamp'] != IMAGE_TIMESTAMP:
        result['reason'] = 'main module base, image size or timestamp does not match supported image'
        return result
    try:
        if dump.read(IMAGE_BASE, 2) != b'MZ':
            raise ValueError('recorded DOS signature mismatch')
        pe_offset = struct.unpack('<I', dump.read(IMAGE_BASE + 0x3C, 4))[0]
        if pe_offset != 0x118 or pe_offset + 24 + 96 > IMAGE_SIZE:
            raise ValueError('recorded PE header offset mismatch')
        header = dump.read(IMAGE_BASE + pe_offset, 24 + 96)
        if header[:4] != b'PE\0\0':
            raise ValueError('recorded PE signature mismatch')
        machine, sections, stamp = struct.unpack_from('<HHI', header, 4)
        optional = 24
        observed = dict(machine=machine, sections=sections, timestamp=stamp,
                        optional_magic=struct.unpack_from('<H', header, optional)[0],
                        entry_rva=struct.unpack_from('<I', header, optional + 16)[0],
                        image_base=struct.unpack_from('<I', header, optional + 28)[0],
                        image_size=struct.unpack_from('<I', header, optional + 56)[0])
        result['header'] = observed
        expected = dict(machine=0x14C, sections=5, timestamp=IMAGE_TIMESTAMP, optional_magic=0x10B,
                        entry_rva=0x3B6172, image_base=IMAGE_BASE, image_size=IMAGE_SIZE)
        if observed != expected:
            raise ValueError('recorded PE header identity mismatch')
        for va, expected_hex, meaning in SITES:
            expected_bytes = bytes.fromhex(expected_hex)
            actual = dump.read(va, len(expected_bytes))
            matched = actual == expected_bytes
            result['fingerprints'].append(dict(address=f'0x{va:08X}', expected_hex=expected_hex,
                                                recorded_hex=actual.hex(), matched=matched, meaning=meaning))
            if not matched:
                raise ValueError(f'recorded original instruction fingerprint mismatch at 0x{va:08X}')
    except (ValueError, struct.error) as error:
        result['reason'] = str(error)
        return result
    result.update(status='supported_layout', reason='recorded PE header and 8 unmodified instruction sites match')
    return result


def identify_candidate(dump: Minidump, expected_candidate: str) -> dict:
    hints = sorted({match.group(1) for m in dump.modules
                    for match in re.finditer(r'(?i)(?:^|[\\/])poc-[^\\/]+-(\d{3})(?:[\\/]|$)', m['name'])})
    historical = dump.sha256 == KNOWN_006_DUMP
    warnings = []
    if historical or '006' in hints:
        warnings.append('Historical 006 snapshot: do not use as evidence of the reported 007 subtitle failure')
    if historical:
        status = 'known_historical_006'
    elif hints and expected_candidate not in hints:
        status = 'different_candidate_path'
        warnings.append('Recorded module paths do not identify the requested candidate')
    else:
        status = 'unknown'
    if expected_candidate in hints:
        warnings.append('Candidate path is only a hint; loaded localization-module artifact hash is not established')
    if len(hints) > 1:
        warnings.append('Multiple candidate directory hints are recorded; do not combine their states')
    return dict(expected_candidate=expected_candidate, directory_hints=hints, status=status,
                known_dump_sha256_match=historical, exact_candidate_match='unknown', warnings=warnings)


def inspect(dump: Minidump, expected_candidate: str = '007') -> dict:
    if not re.fullmatch(r'\d{3}', expected_candidate):
        raise ValueError('expected candidate must be three decimal digits')
    identity = identify_image(dump)
    supported = identity['status'] == 'supported_layout'
    fields = {name: read_field(dump, address, fmt, description) if supported else
              unknown(address, 'unsupported or unverified image layout', description)
              for name, address, fmt, description in FIELDS}
    owner = fields['owner_pointer']
    owner_fields = {}
    pointer = owner['value']
    valid_pointer = owner['status'] == 'recorded' and 0x10000 <= pointer <= 0xFFFFFFB3
    for name, offset in [('audio_handle', 4), ('bs_id', 8), ('flags', 0x48)]:
        if valid_pointer:
            owner_fields[name] = read_field(dump, pointer + offset, 'I')
        else:
            owner_fields[name] = unknown((pointer or 0) + offset, 'owner pointer null, unavailable or outside x86 range')
    return dict(schema=1, dump_path=str(dump.path), dump_sha256=dump.sha256,
                main_image=identity, candidate=identify_candidate(dump, expected_candidate),
                modules=dump.modules, fields=fields, owner_fields=owner_fields,
                limitations=['Recorded snapshot only; no current runtime diagnosis',
                             'Header and instruction fingerprints do not hash the whole loaded executable',
                             'Missing recorded memory remains unknown, not zero',
                             'No subtitle root cause is inferred from field values'],
                process_launched=False, process_attached=False, dump_acquired=False,
                current_runtime_verified=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dump', type=Path, required=True)
    parser.add_argument('--expected-candidate', default='007')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = inspect(Minidump(args.dump), args.expected_candidate)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')
    print('RECORDED SNAPSHOT: ' + report['candidate']['status'] + '; image=' + report['main_image']['status'])
    for warning in report['candidate']['warnings']:
        print('NOTICE: ' + warning)
    for name, row in report['fields'].items():
        print(f"{name}: {row['value'] if row['status'] == 'recorded' else 'unknown'}")
    print('CURRENT RUNTIME: unverified; no root-cause conclusion; no process access')


if __name__ == '__main__':
    main()
