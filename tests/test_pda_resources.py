"""Synthetic PDA resources only: no original game data is needed or embedded."""
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pda_resources import GlyphMarker, PdaResource, Replacement, rebuild_manifest, sha256


def fixture(text=b"Synthetic title", *, shared_fields=False):
    out = bytearray(116)
    struct.pack_into("<8I", out, 0, 32, 40, 44, 52, 1, 1, 1, 1)
    struct.pack_into("<II", out, 32, 2, 56)
    struct.pack_into("<I", out, 40, 0x40000)  # Preserve opaque index flags.
    struct.pack_into("<II", out, 44, 0, 96)
    struct.pack_into("<I", out, 52, 116 + len(text) + 1)
    struct.pack_into("<IhH", out, 56, 72, 2, 0xABCD)
    struct.pack_into("<IhH", out, 64, 72 if shared_fields else 88, 2 if shared_fields else 1, 17)
    struct.pack_into("<Ii", out, 72, 116, -1)
    struct.pack_into("<Ii", out, 80, 0, -3)
    struct.pack_into("<Ii", out, 88, 116, 7)
    struct.pack_into("<4I", out, 96, 5, 1, 1, 1)
    out[112:116] = b"\x81\x82\x83\x84"  # Synthetic opaque image bytes.
    out.extend(text + b"\0synthetic_internal_id\0")
    return bytes(out)


def changed(data, offset, fmt, value):
    out = bytearray(data)
    struct.pack_into(fmt, out, offset, value)
    return bytes(out)


class PdaTest(unittest.TestCase):
    def rebuild(self, source, value, name="p000.r000.s000", expected=None):
        pda = PdaResource(source)
        expected = pda.segments[name].text if expected is None else expected
        return pda.rebuild({name: Replacement(expected, value)}, expected_sha256=sha256(source))

    def test_parse_metadata_and_identifier(self):
        pda = PdaResource(fixture())
        self.assertEqual(pda.page_count, 1)
        self.assertEqual(len(pda.segments), 3)
        self.assertEqual(pda.identifiers, (b"synthetic_internal_id",))
        self.assertEqual(pda.index_values, (0x40000,))
        self.assertEqual(pda.segments["p000.r000.s000"].row_metadata, 0xABCD)
        self.assertEqual(pda.segments["p000.r001.s000"].tag, 7)

    def test_noop_is_byte_identical(self):
        source = fixture()
        self.assertEqual(PdaResource(source).rebuild({}, expected_sha256=sha256(source)), source)
        self.assertEqual(self.rebuild(source, b"Synthetic title"), source)

    def test_growth_preserves_every_other_original_byte(self):
        source = fixture()
        value = b"An expanded synthetic display title"
        result = self.rebuild(source, value)
        self.assertEqual(result[:72], source[:72])
        self.assertEqual(result[76:len(source)], source[76:])
        self.assertEqual(result[len(source):], value + b"\0")
        self.assertEqual(struct.unpack_from("<I", result, 72)[0], len(source))
        pda = PdaResource(result)
        self.assertEqual(pda.segments["p000.r000.s000"].text, value)
        self.assertEqual(pda.segments["p000.r001.s000"].text, b"Synthetic title")
        self.assertEqual(pda.identifiers, PdaResource(source).identifiers)
        self.assertEqual(pda.image_offsets, (96,))

    def test_deterministic_map_order(self):
        source = fixture()
        a = ("p000.r000.s000", Replacement(b"Synthetic title", b"First translation"))
        b = ("p000.r001.s000", Replacement(b"Synthetic title", b"Second translation"))
        pda = PdaResource(source)
        self.assertEqual(pda.rebuild(dict([a, b]), expected_sha256=sha256(source)), pda.rebuild(dict([b, a]), expected_sha256=sha256(source)))

    def test_opaque_non_ascii_storage_is_not_runtime_support(self):
        source = fixture()
        value = bytes([0x80, 0x81, 0x82, 0xA1])
        self.assertEqual(PdaResource(self.rebuild(source, value)).segments["p000.r000.s000"].text, value)

    def test_shared_pointer_field_needs_all_ids(self):
        source = fixture(shared_fields=True)
        with self.assertRaisesRegex(ValueError, "all affected IDs"):
            self.rebuild(source, b"New")
        replacements = {name: Replacement(b"Synthetic title", b"New") for name in ("p000.r000.s000", "p000.r001.s000")}
        output = PdaResource(source).rebuild(replacements, expected_sha256=sha256(source))
        self.assertEqual(PdaResource(output).segments["p000.r001.s000"].text, b"New")
        replacements["p000.r001.s000"] = Replacement(b"Synthetic title", b"Other")
        with self.assertRaisesRegex(ValueError, "conflicting shared"):
            PdaResource(source).rebuild(replacements, expected_sha256=sha256(source))

    def test_source_hash_guard(self):
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            PdaResource(fixture()).rebuild({}, expected_sha256="0" * 64)

    def test_expected_source_guard(self):
        with self.assertRaisesRegex(ValueError, "source bytes mismatch"):
            self.rebuild(fixture(), b"New", expected=b"Wrong")

    def test_unknown_id(self):
        with self.assertRaisesRegex(ValueError, "unknown segment ID"):
            PdaResource(fixture()).rebuild({"bad": Replacement(b"", b"New")}, expected_sha256=sha256(fixture()))

    def test_cannot_replace_image(self):
        with self.assertRaisesRegex(ValueError, "display string"):
            self.rebuild(fixture(), b"New", "p000.r000.s001", b"")

    def test_reject_embedded_nul_and_unexpected_empty(self):
        for value in (b"A\0B", b""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.rebuild(fixture(), value)

    def test_controls_preserved_exactly_in_order(self):
        source = fixture(b"Press \x0bE then \x0bJ: %s {name}\n")
        value = b"Use \x0bE and \x0bJ: %s {name}\n"
        self.assertEqual(PdaResource(self.rebuild(source, value)).segments["p000.r000.s000"].text, value)
        for value in (b"Use \x0bK and \x0bJ: %s {name}\n", b"Use \x0bJ and \x0bE: %s {name}\n", b"Use \x0bE and \x0bJ: %d {name}\n", b"Use \x0bE and \x0bJ: %s {other}\n", b"Use \x0bE and \x0bJ: %s {name}"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "protected token"):
                self.rebuild(source, value)

    def test_glyph_marker_requires_explicit_approval(self):
        source = fixture(b"Press \x0bE")
        replacement = {"p000.r000.s000": Replacement(b"Press \x0bE", b"\x1f0001\x1f0002 \x0bE")}
        pda = PdaResource(source)
        with self.assertRaisesRegex(ValueError, "protected token"):
            pda.rebuild(replacement, expected_sha256=sha256(source))
        result = pda.rebuild(replacement, expected_sha256=sha256(source), glyph_marker=GlyphMarker(b"\x1f", 4, 10))
        self.assertEqual(PdaResource(result).segments["p000.r000.s000"].text, replacement["p000.r000.s000"].value)
        self.assertEqual(result, pda.replace(replacement, glyph_marker=0x1F))

    def test_glyph_marker_does_not_exempt_original_controls(self):
        source = fixture(b"Press \x0bE")
        for value in (b"\x1f0001", b"\x1f0001\x0bK", b"\x1f0011\x0bE", b"\x1f001\x0bE", b"\x1fabcd\x0bE"):
            replacement = {"p000.r000.s000": Replacement(b"Press \x0bE", value)}
            with self.subTest(value=value), self.assertRaises(ValueError):
                PdaResource(source).rebuild(replacement, expected_sha256=sha256(source), glyph_marker=GlyphMarker(b"\x1f", 4, 10))

    def test_glyph_marker_source_collision(self):
        source = fixture(b"Press \x1f0001")
        with self.assertRaisesRegex(ValueError, "collides"):
            PdaResource(source).rebuild({"p000.r000.s000": Replacement(b"Press \x1f0001", b"\x1f0002")}, expected_sha256=sha256(source), glyph_marker=GlyphMarker(b"\x1f", 4, 10))

    def test_glyph_marker_must_not_split_original_token(self):
        for expected, value in ((b"%s", b"%\x1f0001s"), (b"\x0bE", b"\x0b\x1f0001E"), (b"{name}", b"{na\x1f0001me}")):
            source = fixture(expected)
            with self.subTest(expected=expected), self.assertRaisesRegex(ValueError, "protected token"):
                PdaResource(source).replace({"p000.r000.s000": Replacement(expected, value)}, glyph_marker=0x1F)

    def test_invalid_glyph_marker_declaration(self):
        for spec in ((b"\0", 4, 10), (b"AA", 4, 10), (b"\x1f", 0, 10), (b"\x1f", 4, 10000), (b"\x1f", 4, -1)):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                GlyphMarker(*spec)

    def test_header_and_table_bounds(self):
        for source in (b"", bytes(31), changed(fixture(), 0, "<I", 0xFFFFFFFC), changed(fixture(), 16, "<I", 0xFFFFFFFF), changed(fixture(), 32, "<I", 0xFFFFFFFF)):
            with self.subTest(source=source[:32]), self.assertRaises(ValueError):
                PdaResource(source)

    def test_overlapping_tables(self):
        with self.assertRaisesRegex(ValueError, "overlapping"):
            PdaResource(changed(fixture(), 4, "<I", 32))

    def test_misaligned_table(self):
        with self.assertRaisesRegex(ValueError, "table offset"):
            PdaResource(changed(fixture(), 0, "<I", 33))

    def test_negative_segment_count(self):
        with self.assertRaisesRegex(ValueError, "negative segment"):
            PdaResource(changed(fixture(), 60, "<h", -1))

    def test_bad_string_offset_or_structural_pointer(self):
        for offset in (31, 32, 0xFFFFFFFF):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                PdaResource(changed(fixture(), 72, "<I", offset))

    def test_unterminated_identifier(self):
        with self.assertRaisesRegex(ValueError, "unterminated"):
            PdaResource(fixture()[:-1])

    def test_null_text_preserved_but_not_replaceable(self):
        source = changed(fixture(), 72, "<I", 0)
        self.assertIsNone(PdaResource(source).segments["p000.r000.s000"].text)
        with self.assertRaisesRegex(ValueError, "display string"):
            self.rebuild(source, b"New", expected=b"")

    def test_opaque_numeric_segment_is_not_an_image_index(self):
        pda = PdaResource(changed(fixture(), 80, "<I", 0x1234))
        self.assertEqual(pda.segments["p000.r000.s001"].value, 0x1234)
        self.assertIsNone(pda.segments["p000.r000.s001"].text)

    def test_image_descriptor_segment(self):
        source = changed(changed(fixture(), 84, "<i", -2), 80, "<I", 44)
        self.assertIsNone(PdaResource(source).segments["p000.r000.s001"].text)
        for offset in (43, 45, 52):
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "image descriptor"):
                PdaResource(changed(source, 80, "<I", offset))

    def test_invalid_image_header(self):
        for source in (changed(fixture(), 48, "<I", 0), changed(fixture(), 48, "<I", len(fixture()) - 2)):
            with self.subTest(source=source[:52]), self.assertRaises(ValueError):
                PdaResource(source)

    def test_manifest_roundtrip_and_duplicates(self):
        source = fixture()
        entry = {"id": "p000.r000.s000", "expected_hex": b"Synthetic title".hex(), "replacement_hex": b"Longer synthetic title".hex()}
        manifest = {"format": "second-sight-pda-replacements-v1", "source_sha256": sha256(source), "replacements": [entry]}
        self.assertEqual(rebuild_manifest(source, manifest), self.rebuild(source, b"Longer synthetic title"))
        manifest["replacements"].append(entry)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            rebuild_manifest(source, manifest)

    def test_cli_copy_and_no_overwrite(self):
        script = Path(__file__).resolve().parents[1] / "tools" / "pda_resources.py"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.raw"
            source.write_bytes(fixture())
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"format": "second-sight-pda-replacements-v1", "source_sha256": sha256(fixture()), "replacements": []}), encoding="utf-8")
            output = root / "output.raw"
            result = subprocess.run([sys.executable, str(script), "rebuild", str(source), str(manifest), str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_bytes(), fixture())
            result = subprocess.run([sys.executable, str(script), "rebuild", str(source), str(manifest), str(source)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(source.read_bytes(), fixture())


if __name__ == "__main__":
    unittest.main()
