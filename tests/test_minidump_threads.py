"""Synthetic recorded contexts only: no process or proprietary dump required."""
import importlib.util
import os
from pathlib import Path
import struct
import tempfile
import unittest

SOURCE = Path(os.environ.get('MINIDUMP_READER', Path(__file__).resolve().parents[1] / 'tools/minidump_reader.py'))
SPEC = importlib.util.spec_from_file_location('reader_under_test', SOURCE)
READER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(READER)


def fixture(arch=0, wow=False, recorded=True):
    data = bytearray(0x3000)
    data[:4] = b'MDMP'
    struct.pack_into('<II', data, 8, 3, 32)
    for index, row in enumerate([(7, 56, 80), (3, 52, 136), (5, 20, 188)]):
        struct.pack_into('<III', data, 32 + 12 * index, *row)
    struct.pack_into('<H', data, 80, arch)
    struct.pack_into('<I', data, 136, 1)
    size = 716 if arch == 0 else 1232
    struct.pack_into('<IIIIQQIIII', data, 140, 7, 0, 0, 0, 0x1000,
                     0x8000, 0, 0, size, 0x100)
    struct.pack_into('<I', data, 188, 1)
    struct.pack_into('<QII', data, 192, 0x1000, 0x2000 if recorded else 0, 0x1000)
    if arch == 0:
        struct.pack_into('<I', data, 0x100, 0x10007)
        for offset, value in [(184, 0x401234), (196, 0x8000), (180, 0x8010)]:
            struct.pack_into('<I', data, 0x100 + offset, value)
    else:
        struct.pack_into('<I', data, 0x130, 0x10001f)
        struct.pack_into('<Q', data, 0x100 + 248, 0x7ffa12345678)
    if wow:
        struct.pack_into('<Q', data, 0x1000 + 0x1488, 0x1800)
        struct.pack_into('<I', data, 0x1804, 0x10007)
        struct.pack_into('<I', data, 0x1804 + 184, 0x401234)
        struct.pack_into('<I', data, 0x1804 + 196, 0x8000)
    return data


class RecordedThreadTests(unittest.TestCase):
    def parse(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.dmp'
            path.write_bytes(data)
            return READER.Minidump(path)

    def test_non_exception_dump_is_valid(self):
        self.assertIsNone(self.parse(fixture()).exception())

    def test_x86_thread_context(self):
        row = self.parse(fixture()).threads()[0]
        self.assertEqual(row['context']['registers']['eip'], 0x401234)
        self.assertEqual(row['context']['architecture'], 'x86')
        self.assertEqual(row['id'], 7)

    def test_amd64_context_is_not_decoded_as_x86(self):
        row = self.parse(fixture(9)).threads()[0]
        self.assertEqual(row['context']['registers']['rip'], 0x7ffa12345678)
        self.assertEqual(row['context']['architecture'], 'amd64')
        self.assertIsNone(row['wow64_context'])

    def test_explicit_wow64_recovery(self):
        row = self.parse(fixture(9, wow=True)).threads(wow64=True)[0]
        self.assertEqual(row['wow64_context']['registers']['eip'], 0x401234)
        self.assertEqual(row['wow64_context']['recorded_address'], 0x1804)

    def test_wow64_missing_memory_is_unknown(self):
        row = self.parse(fixture(9, recorded=False)).threads(wow64=True)[0]
        self.assertIsNone(row['wow64_context'])
        self.assertIn('not recorded', row['wow64_error'])

    def test_bad_wow64_flags_are_rejected(self):
        data = fixture(9, wow=True)
        struct.pack_into('<I', data, 0x1804, 0x10001f)
        row = self.parse(data).threads(wow64=True)[0]
        self.assertIsNone(row['wow64_context'])
        self.assertIn('x86', row['wow64_error'])

    def test_partial_x86_context_is_not_invented(self):
        data = fixture()
        struct.pack_into('<I', data, 140 + 40, 100)
        row = self.parse(data).threads()[0]
        self.assertIsNone(row['context'])
        self.assertIn('context', row['context_error'])

    def test_thread_table_count_is_bounded(self):
        data = fixture()
        struct.pack_into('<I', data, 136, 2)
        with self.assertRaisesRegex(ValueError, 'thread list'):
            self.parse(data).threads()

    def test_duplicate_thread_id_is_rejected(self):
        data = fixture()
        struct.pack_into('<III', data, 32 + 12, 3, 100, 0x700)
        struct.pack_into('<I', data, 0x700, 2)
        data[0x704:0x734] = data[140:188]
        data[0x734:0x764] = data[140:188]
        with self.assertRaisesRegex(ValueError, 'duplicate thread'):
            self.parse(data).threads()

    def test_unknown_system_architecture_stays_unknown(self):
        row = self.parse(fixture(12)).threads()[0]
        self.assertIsNone(row['context'])
        self.assertIn('architecture', row['context_error'])

    def exception_fixture(self, arch):
        data = fixture(arch)
        data[0x600:0x624] = data[32:68]
        struct.pack_into('<II', data, 8, 4, 0x600)
        struct.pack_into('<III', data, 0x624, 6, 168, 0x900)
        struct.pack_into('<I', data, 0x900, 7)
        struct.pack_into('<I', data, 0x908, 0xc0000005)
        struct.pack_into('<Q', data, 0x918, 0x401234)
        size = 716 if arch == 0 else 1232
        struct.pack_into('<II', data, 0x9a0, size, 0xa00)
        data[0xa00:0xa00 + size] = data[0x100:0x100 + size]
        return data

    def test_x86_exception_backward_compatibility(self):
        row = self.parse(self.exception_fixture(0)).exception()
        self.assertEqual(row['registers']['eip'], 0x401234)
        self.assertEqual(row['context_architecture'], 'x86')

    def test_amd64_exception_does_not_block_threads(self):
        dump = self.parse(self.exception_fixture(9))
        self.assertEqual(dump.exception()['registers']['rip'], 0x7ffa12345678)
        self.assertEqual(len(dump.threads()), 1)

    def test_unknown_exception_context_preserves_metadata(self):
        data = self.exception_fixture(9)
        struct.pack_into('<I', data, 0xa30, 0)
        row = self.parse(data).exception()
        self.assertIsNone(row['registers'])
        self.assertEqual(row['code'], 0xc0000005)
        self.assertIn('unsupported', row['context_error'])


if __name__ == '__main__':
    unittest.main()
