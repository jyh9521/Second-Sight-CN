"""Read-only, version-locked audit of the first Isolation dialogue routes.

This is a game adapter, not a subtitle implementation or runtime test. Reports
contain source fingerprints rather than the proprietary source dialogue.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from assess_resources import Pak, StringTable, require
from locale_catalog import load_catalog


EXE_SHA256 = '4092a8d1fb042dffe9fb95e2185f32cb80390299145e8d453a5e909a06d35fda'
BS_SHA256 = 'e72b56066e8b68fb23ac2833b58376a18a506503e02e83864727eef1fbc03a7d'
SAMPLE_IDS = (2472, 2473, 2474, 2475, 2508)
SITES = (
    (0x5644DF, 'c74208a8090000', 'level state current BS ID = 2472'),
    (0x5644E6, 'c7420cab090000', 'level state last BS ID = 2475'),
    (0x5644ED, 'c74210a9090000', 'level state repeated BS ID = 2473'),
    (0x5629F1, '8b47083b470c8d77087d0340eb5c', 'advance current ID toward last ID'),
    (0x562A6E, '8b0e51e81af30400', 'send current BS ID to player speech wrapper 0x5B1D90'),
    (0x5B1DBF, '508b42208b88bc000000516affe8af18eaff', 'wrapper sends BS ID to 0x453680'),
    (0x563B04, 'bfcc090000', 'NPC initial BS ID = 2508'),
    (0x563B5A, '57516affe81dfbeeff', 'NPC sends BS ID to 0x453680'),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bind_sample(strings: list[bytes], rows: list[dict], ids=SAMPLE_IDS) -> list[dict]:
    """Require source identity; never mistake target presence for acceptance."""
    by_id = {row['id']: row for row in rows}
    require(len(by_id) == len(rows), 'duplicate BS catalog ID')
    result = []
    for key in ids:
        require(0 < key < len(strings), f'BS:{key}: invalid ID')
        require(key in by_id, f'BS:{key}: missing translation')
        row, source = by_id[key], strings[key]
        require(bool(row.get('target')), f'BS:{key}: missing target')
        expected = row.get('source_sha256')
        if expected is None:
            expected = sha256(row['source'].encode('cp1252'))
        require(sha256(source) == expected, f'BS:{key}: source hash mismatch')
        result.append(dict(id=key, source_sha256=expected, target=row['target'],
                           catalog_status=row.get('status'),
                           review_status=row.get('review_status'),
                           source_bound=True, runtime_verified=False))
    return result


def verify_sites(read_bytes) -> list[dict]:
    result = []
    for va, expected_hex, meaning in SITES:
        expected = bytes.fromhex(expected_hex)
        actual = read_bytes(va, len(expected))
        require(actual == expected, f'original bytes mismatch at 0x{va:08X}')
        result.append(dict(va=f'0x{va:08X}', original_hex=actual.hex(), meaning=meaning))
    return result


def inspect(game: Path, locale: Path) -> dict:
    import pefile

    exe_path = game / 'secondsight.EXE'
    archive_path = game / 'pak' / 'arcade' / 'l_103.pak'
    exe = exe_path.read_bytes()
    require(sha256(exe) == EXE_SHA256, 'unsupported executable hash')
    archive = archive_path.read_bytes()
    bs = Pak(archive).member('data/strsspxe.bs')
    require(sha256(bs) == BS_SHA256, 'unsupported BS hash')
    strings = StringTable(bs).strings
    catalog = load_catalog(locale)
    pe = pefile.PE(data=exe, fast_load=True)
    def read(va, size):
        off = pe.get_offset_from_rva(va - pe.OPTIONAL_HEADER.ImageBase)
        return exe[off:off + size]
    sites = verify_sites(read)
    result = dict(
        schema=1, method='offline static audit; no target execution or attachment',
        executable=dict(path=str(exe_path.resolve()), sha256=sha256(exe)),
        archive=dict(path=str(archive_path.resolve()), sha256=sha256(archive)),
        bs=dict(member='data/strsspxe.bs', sha256=sha256(bs), entries=len(strings)),
        locale=str(locale.resolve()), samples=bind_sample(strings, catalog['bs']),
        sites=sites,
        proven_edges=[['0x562A71', '0x5B1D90'], ['0x5B1DCC', '0x453680'],
                      ['0x563B5E', '0x453680']],
        vm_candidates=[
            dict(archive='pak/vm/lv60_raw.pak', member='vm/scripts/lv60_docinguardsquarters.raw',
                 offset='0x180', integer=2521, following_call_opcode='0x6E'),
            dict(archive='pak/vm/lv60_raw.pak', member='vm/scripts/lv60_lockedin.raw',
                 integers=list(range(2566, 2573)), following_call_opcode='0x6E')],
        limitations=[
            'VM candidate opcode/ID binding is not established by this audit',
            'Only the selected five lines are bound; no whole-game runtime coverage claim',
            'Does not prove a caption event is queued, rendered, timed or visible',
            'Catalog target presence is separate from editorial review and runtime acceptance'],
        game_launched=False, game_attached=False, game_files_written=False,
        runtime_verified=False)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', required=True, type=Path)
    parser.add_argument('--locale', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    report = inspect(args.game, args.locale)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print('PASS: 5 source-bound dialogue samples; 8 original-byte sites; runtime unverified')


if __name__ == '__main__':
    main()
