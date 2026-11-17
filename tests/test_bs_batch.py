import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from assess_resources import StringTable


class BatchBsTests(unittest.TestCase):
    def setUp(self):
        self.raw = struct.pack('<4I', 16, 17, 17, 23) + b'\0hello\0bye\0'
        self.table = StringTable(self.raw)

    def test_batch_preserves_unselected_alias_and_pool(self):
        result = self.table.replace_many({1: b'\x1f0001', 3: b'longer text'})
        parsed = StringTable(result)
        self.assertEqual(parsed.strings, [b'', b'\x1f0001', b'hello', b'longer text'])
        self.assertEqual(result[16:len(self.raw)], self.raw[16:])
        self.assertEqual(self.table.data, self.raw)

    def test_no_change_is_byte_exact(self):
        self.assertEqual(self.table.replace_many({}), self.raw)
        self.assertEqual(self.table.replace_many({1: b'hello'}), self.raw)

    def test_bad_ids_or_terminators_fail(self):
        for replacements in [{0: b'x'}, {4: b'x'}, {-1: b'x'}, {1: b'a\0b'}, {1: 'text'}]:
            with self.assertRaises(ValueError): self.table.replace_many(replacements)


if __name__ == '__main__':
    unittest.main()
