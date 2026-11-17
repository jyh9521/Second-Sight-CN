"""Synthetic PE/module/memory records; no proprietary dump or live process."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from inspect_subtitle_dump import (FIELDS, IMAGE_BASE, IMAGE_SIZE, IMAGE_TIMESTAMP,
                                   KNOWN_006_DUMP, SITES, inspect)
from minidump_reader import Minidump


def fixture(*, candidate='007', base=IMAGE_BASE, image_size=IMAGE_SIZE,
            owner=0, missing_field=None, bad_fingerprint=False, bad_header=False,
            duplicate_module=False, owner_partial=False, fade=0.5):
    data = bytearray(56)
    data[:4] = b'MDMP'
    struct.pack_into('<II', data, 8, 2, 32)
    def allocate(raw):
        offset = len(data)
        data.extend(raw)
        return offset
    count = 2 if duplicate_module else 1
    module_offset = allocate(bytearray(4 + 108 * count))
    struct.pack_into('<I', data, module_offset, count)
    name = fr'C:\fixture\poc-zh-CN-{candidate}\game\secondsight.EXE'.encode('utf-16le')
    name_rva = allocate(struct.pack('<I', len(name)) + name)
    for index in range(count):
        struct.pack_into('<QIIII', data, module_offset + 4 + 108 * index,
                         base, image_size, 0, IMAGE_TIMESTAMP, name_rva)
    header = bytearray(0x400)
    header[:2] = b'MZ'
    struct.pack_into('<I', header, 0x3C, 0x118)
    header[0x118:0x11C] = b'PE\0\0'
    struct.pack_into('<HHI', header, 0x11C, 0x14C, 5, IMAGE_TIMESTAMP)
    optional = 0x118 + 24
    struct.pack_into('<H', header, optional, 0x20B if bad_header else 0x10B)
    struct.pack_into('<I', header, optional + 16, 0x3B6172)
    struct.pack_into('<I', header, optional + 28, IMAGE_BASE)
    struct.pack_into('<I', header, optional + 56, IMAGE_SIZE)
    ranges = [(IMAGE_BASE, header)]
    for index, (va, value, _) in enumerate(SITES):
        raw = bytes.fromhex(value)
        if bad_fingerprint and index == 0:
            raw = b'\x90' * len(raw)
        ranges.append((va, raw))
    for name, va, fmt, _ in FIELDS:
        if name == missing_field:
            continue
        value = owner if name == 'owner_pointer' else fade if fmt == 'f' else 0
        ranges.append((va, struct.pack('<' + fmt, value)))
    if 0x10000 <= owner <= 0xFFFFFFB3:
        ranges += [(owner + 4, struct.pack('<I', 123)), (owner + 8, struct.pack('<I', 2473))]
        if not owner_partial:
            ranges.append((owner + 0x48, struct.pack('<I', 0x20)))
    memory_offset = allocate(bytearray(4 + 16 * len(ranges)))
    struct.pack_into('<I', data, memory_offset, len(ranges))
    for index, (address, raw) in enumerate(ranges):
        offset = allocate(raw)
        struct.pack_into('<QII', data, memory_offset + 4 + 16 * index, address, len(raw), offset)
    struct.pack_into('<III', data, 32, 4, 4 + 108 * count, module_offset)
    struct.pack_into('<III', data, 44, 5, 4 + 16 * len(ranges), memory_offset)
    return data


class SubtitleDumpTests(unittest.TestCase):
    def read(self, **kwargs):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'synthetic.dmp'
            path.write_bytes(fixture(**kwargs))
            return Minidump(path)

    def test_supported_image_and_fields(self):
        report = inspect(self.read())
        self.assertEqual(report['main_image']['status'], 'supported_layout')
        self.assertEqual(report['fields']['mode']['value'], 0)
        self.assertEqual(report['fields']['fade']['value'], 0.5)
        self.assertFalse(report['current_runtime_verified'])
        self.assertEqual(report['candidate']['exact_candidate_match'], 'unknown')

    def test_historical_006_is_not_007(self):
        dump = self.read(candidate='006')
        dump.sha256 = KNOWN_006_DUMP
        report = inspect(dump)
        self.assertEqual(report['candidate']['status'], 'known_historical_006')
        self.assertTrue(any('007' in text for text in report['candidate']['warnings']))
        self.assertFalse(report['current_runtime_verified'])

    def test_006_path_without_known_hash_stays_different_candidate(self):
        report = inspect(self.read(candidate='006'))
        self.assertEqual(report['candidate']['status'], 'different_candidate_path')
        self.assertFalse(report['candidate']['known_dump_sha256_match'])

    def test_wrong_base_does_not_decode_absolute_fields(self):
        report = inspect(self.read(base=0x500000))
        self.assertEqual(report['main_image']['status'], 'unknown')
        self.assertEqual(report['fields']['mode']['status'], 'unknown')
        self.assertIsNone(report['fields']['mode']['value'])

    def test_wrong_image_size_does_not_decode(self):
        self.assertEqual(inspect(self.read(image_size=0x1000))['fields']['mode']['status'], 'unknown')

    def test_header_drift_does_not_decode(self):
        self.assertEqual(inspect(self.read(bad_header=True))['fields']['mode']['status'], 'unknown')

    def test_instruction_drift_does_not_decode(self):
        self.assertEqual(inspect(self.read(bad_fingerprint=True))['fields']['mode']['status'], 'unknown')

    def test_missing_field_is_not_zero(self):
        row = inspect(self.read(missing_field='display_gate'))['fields']['display_gate']
        self.assertEqual(row['status'], 'unknown')
        self.assertIsNone(row['value'])

    def test_owner_reads_only_recorded_fields(self):
        report = inspect(self.read(owner=0x10000000, owner_partial=True))
        self.assertEqual(report['owner_fields']['bs_id']['value'], 2473)
        self.assertEqual(report['owner_fields']['flags']['status'], 'unknown')

    def test_null_and_overflow_owner_are_unknown(self):
        for owner in (0, 0xFFFFFFFC):
            with self.subTest(owner=owner):
                report = inspect(self.read(owner=owner))
                self.assertTrue(all(r['status'] == 'unknown' for r in report['owner_fields'].values()))

    def test_duplicate_identical_module_is_not_ambiguous(self):
        image = inspect(self.read(duplicate_module=True))['main_image']
        self.assertEqual(image['recorded_matches'], 2)
        self.assertEqual(image['unique_matches'], 1)
        self.assertEqual(image['status'], 'supported_layout')

    def test_nonfinite_float_is_unknown(self):
        self.assertEqual(inspect(self.read(fade=float('nan')))['fields']['fade']['status'], 'unknown')


if __name__ == '__main__':
    unittest.main()
