from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from make_host_fixture import fixture


class HostFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.legacy = fixture()
        cls.current = fixture('SLP3')

    def test_default_keeps_legacy_slp2_fixture(self):
        self.assertEqual(self.legacy[:4], b'SLP2')
        self.assertEqual(struct.unpack_from('<IIII', self.legacy, 4), (1, 1, 7, 2))

    def test_slp3_alias_section_leaves_primary_records_and_resources_unchanged(self):
        self.assertEqual(self.current[:4], b'SLP3')
        self.assertEqual(struct.unpack_from('<IIIII', self.current, 4), (1, 1, 7, 2, 2))
        at = 24
        def number():
            nonlocal at
            value = struct.unpack_from('<I', self.current, at)[0]
            at += 4
            return value
        def blob():
            nonlocal at
            length = number()
            value = self.current[at:at+length]
            at += length
            return value
        for _ in range(4):
            number(); blob(); blob()
        alias_start = at
        self.assertEqual([(number(), blob()) for _ in range(2)],
                         [(850, b'Synthetic menu variant A'), (850, b'Synthetic menu variant B')])
        # Dropping only the aliases and their header field recovers SLP2 exactly.
        stripped = b'SLP2' + self.current[4:20] + self.current[24:alias_start] + self.current[at:]
        self.assertEqual(stripped, self.legacy)

    def test_unknown_format_rejected(self):
        with self.assertRaises(ValueError): fixture('SLP4')


if __name__ == '__main__': unittest.main()
