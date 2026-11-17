"""Synthetic format regression tests; no original assets required."""
import struct
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from assess_resources import Pak, StringTable


def bs():
    return struct.pack("<3I", 12, 13, 13) + b"\0ABC\0"


def pak():
    payload = bs()
    toc = 48
    return struct.pack("<4sIII", b"P4CK", toc, 16, 5) + payload + bytes(toc - 16 - len(payload)) + struct.pack("<4I", 16, 16, len(payload), 0) + b"a.bs\0"


class FormatsTest(unittest.TestCase):
    def test_bs_ids_and_alias(self):
        self.assertEqual(StringTable(bs()).strings, [b"", b"ABC", b"ABC"])

    def test_bs_roundtrip(self):
        self.assertEqual(StringTable(bs()).replace(1, b"ABC"), bs())

    def test_bs_growing_independent_alias(self):
        modified = StringTable(bs()).replace(1, b"A longer string")
        self.assertEqual(StringTable(modified).strings, [b"", b"A longer string", b"ABC"])

    def test_bs_opaque_multibyte_storage_not_rendering(self):
        value = "汉字".encode("utf-8")
        self.assertEqual(StringTable(StringTable(bs()).replace(1, value)).strings[1], value)

    def test_bs_bad_offset(self):
        with self.assertRaises(ValueError):
            StringTable(struct.pack("<3I", 12, 500, 13) + b"\0ABC\0")

    def test_bs_unterminated(self):
        with self.assertRaises(ValueError):
            StringTable(bs()[:-1])

    def test_bs_embedded_null(self):
        with self.assertRaises(ValueError):
            StringTable(bs()).replace(1, b"A\0B")

    def test_bs_index_bounds(self):
        with self.assertRaises(ValueError):
            StringTable(bs()).replace(-1, b"A")
        with self.assertRaises(ValueError):
            StringTable(bs()).replace(0, b"changed anchor")

    def test_pak_read_roundtrip(self):
        self.assertEqual(Pak(pak()).member("a.bs"), bs())
        self.assertEqual(Pak(pak()).replace("a.bs", bs()), pak())

    def test_pak_growth(self):
        payload = StringTable(bs()).replace(1, b"Long text")
        self.assertEqual(Pak(Pak(pak()).replace("a.bs", payload)).member("a.bs"), payload)

    def test_pak_truncated(self):
        with self.assertRaises(ValueError):
            Pak(pak()[:-1])

    def test_pak_payload_bounds(self):
        value = bytearray(pak())
        struct.pack_into("<I", value, 48 + 8, 500)
        with self.assertRaises(ValueError):
            Pak(bytes(value))

    def test_pak_unknown_flag(self):
        value = bytearray(pak())
        struct.pack_into("<I", value, 48 + 12, 1)
        with self.assertRaises(ValueError):
            Pak(bytes(value)).replace("a.bs", b"different")

    def test_pak_bad_alignment(self):
        with self.assertRaises(ValueError):
            Pak(pak()).replace("a.bs", b"different", 3)

    def test_pak_duplicate_names_preserved_but_lookup_rejected(self):
        data = bytearray(pak()[:48])
        struct.pack_into("<I", data, 8, 32)
        data.extend(struct.pack("<4I", 32, 16, len(bs()), 0) * 2 + b"a.bs\0")
        parsed = Pak(bytes(data))
        self.assertEqual(len(parsed.entries), 2)
        with self.assertRaises(ValueError):
            parsed.member("a.bs")


if __name__ == "__main__":
    unittest.main()
