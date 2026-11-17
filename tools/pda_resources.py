"""Lossless, locale-neutral PDA resource inspection and append/repoint rebuilding.

The input is an unrelocated data/pdaps_?.raw resource, not a runtime memory dump.
String bytes remain opaque: encoding and glyph support belong to the caller.
See docs/research/PDA_FORMAT.md for verified structure and runtime limitations.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct
from typing import Mapping


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def protected_tokens(value: bytes) -> tuple[bytes, ...]:
    """Keep control bytes and their opcode, printf and brace placeholders ordered.

    Observed PDA escapes begin with VT (0x0b) followed by one opcode byte.
    This deliberately does not interpret an opcode or change whitespace.
    """
    token = rb"\x0b[\s\S]|[\x01-\x1f\x7f]|%(?:\d+\$)?[-+#0 ]*(?:\d+|\*)?(?:\.(?:\d+|\*))?(?:hh|ll|[hlLzjt])?[diouxXeEfFgGaAcspn%]|\{[A-Za-z_0-9][^{}]*\}"
    return tuple(re.findall(token, value))


@dataclass(frozen=True)
class Segment:
    id: str
    page: int
    row: int
    segment: int
    field_offset: int
    value: int
    tag: int
    row_metadata: int
    text: bytes | None


@dataclass(frozen=True)
class Replacement:
    expected: bytes
    value: bytes


@dataclass(frozen=True)
class GlyphMarker:
    """Explicit renderer contract, not an automatic exemption for control bytes."""
    prefix: bytes
    digits: int
    max_id: int

    def __post_init__(self) -> None:
        require(isinstance(self.prefix, bytes) and len(self.prefix) == 1 and 0 < self.prefix[0] < 32, "glyph prefix must be one non-NUL control byte")
        require(type(self.digits) is int and 1 <= self.digits <= 8, "glyph marker digits must be 1..8")
        require(type(self.max_id) is int and 0 <= self.max_id < 10 ** self.digits, "invalid maximum glyph ID")

    def control_view(self, value: bytes) -> bytes:
        out = bytearray()
        cursor = 0
        while cursor < len(value):
            if value[cursor:cursor + 1] != self.prefix:
                out.append(value[cursor])
                cursor += 1
                continue
            digits = value[cursor + 1:cursor + 1 + self.digits]
            require(len(digits) == self.digits and all(48 <= byte <= 57 for byte in digits), "malformed glyph marker")
            require(int(digits) <= self.max_id, "glyph marker ID exceeds approved atlas")
            # A visible sentinel prevents removal from joining a split control
            # token (e.g. '%' + glyph + 's') into a falsely valid '%s'.
            out.append(ord("?"))
            cursor += 1 + self.digits
        return bytes(out)


class PdaResource:
    """Parse known pointer tables without modifying or decoding source bytes."""

    def __init__(self, data: bytes):
        require(isinstance(data, bytes), "PDA input must be immutable bytes")
        require(32 <= len(data) <= 0xFFFFFFFF, "invalid PDA file size")
        self.data = data
        self.header = struct.unpack_from("<8I", data)
        pages, indices, images, identifiers, np, ni, nm, nk = self.header
        self.page_count = np
        self.image_count = nm
        self._regions: list[tuple[int, int, str]] = [(0, 32, "header")]
        self._claim(pages, np, 8, "pages")
        self._claim(indices, ni, 4, "indices")
        self._claim(images, nm, 8, "images")
        self._claim(identifiers, nk, 4, "identifiers")
        self.index_values = tuple(struct.unpack_from("<I", data, indices + i * 4)[0] for i in range(ni))
        pending: list[tuple[int, int, int, int, int, int, int]] = []
        rows_seen = 0
        for p in range(np):
            count, offset = struct.unpack_from("<II", data, pages + p * 8)
            self._claim(offset, count, 8, "rows")
            rows_seen += count
            require(rows_seen <= len(data) // 8, "excessive row references")
            for r in range(count):
                start, size, metadata = struct.unpack_from("<IhH", data, offset + r * 8)
                require(size >= 0, "negative segment count")
                self._claim(start, size, 8, "segments")
                require(len(pending) + size <= len(data) // 8, "excessive segment references")
                for s in range(size):
                    field = start + s * 8
                    value, tag = struct.unpack_from("<Ii", data, field)
                    pending.append((p, r, s, field, value, tag, metadata))
        self._validate_regions()
        self.image_offsets = tuple(struct.unpack_from("<I", data, images + i * 8 + 4)[0] for i in range(nm))
        for offset in self.image_offsets:
            require(offset != 0 and offset + 16 <= len(data), "image header outside file")
            self._check_payload(offset, offset + 16, "image header")
        self.identifier_offsets = tuple(struct.unpack_from("<I", data, identifiers + i * 4)[0] for i in range(nk))
        self.identifiers = tuple(self._string(offset, "identifier") for offset in self.identifier_offsets)
        self.segments: dict[str, Segment] = {}
        for p, r, s, field, value, tag, metadata in pending:
            name = f"p{p:03d}.r{r:03d}.s{s:03d}"
            text = None if tag in (-3, -2) or value == 0 else self._string(value, name)
            if tag == -2:
                require(images <= value < images + nm * 8 and (value - images) % 8 == 0, f"{name}: image descriptor reference outside image table")
            self.segments[name] = Segment(name, p, r, s, field, value, tag, metadata, text)

    def _claim(self, offset: int, count: int, stride: int, kind: str) -> None:
        require(count <= len(self.data) // stride, f"{kind}: excessive count")
        if count == 0:
            require(offset == 0 or 32 <= offset <= len(self.data), f"{kind}: invalid empty table")
            return
        require(offset >= 32 and offset % 4 == 0, f"{kind}: invalid table offset")
        end = offset + count * stride
        require(end <= len(self.data), f"{kind}: table outside file")
        self._regions.append((offset, end, kind))

    def _validate_regions(self) -> None:
        # Identical shared tables are allowed; partial or cross-kind overlap is not.
        regions = sorted(set(self._regions))
        for previous, current in zip(regions, regions[1:]):
            require(previous[1] <= current[0], f"overlapping {previous[2]} and {current[2]} tables")
        self._regions = regions

    def _check_payload(self, start: int, end: int, name: str) -> None:
        require(all(end <= low or start >= high for low, high, _ in self._regions), f"{name}: payload overlaps structural table")

    def _string(self, offset: int, name: str) -> bytes:
        require(32 <= offset < len(self.data), f"{name}: string offset outside file")
        end = self.data.find(b"\0", offset)
        require(end >= 0, f"{name}: unterminated string")
        self._check_payload(offset, end + 1, name)
        return self.data[offset:end]

    def rebuild(self, replacements: Mapping[str, Replacement], *, expected_sha256: str, glyph_marker: GlyphMarker | None = None) -> bytes:
        """Append changed strings, then update their pointer fields only.

        Every call checks the source hash and each source string. Empty/no-op
        replacement maps return the original bytes exactly. String aliases are
        independent unless their *pointer field* is itself shared; shared fields
        require all corresponding IDs to be changed to the same value.
        """
        require(sha256(self.data) == expected_sha256.lower(), "PDA source SHA-256 mismatch")
        fields: dict[int, bytes] = {}
        for name, replacement in replacements.items():
            require(name in self.segments, f"unknown segment ID: {name}")
            segment = self.segments[name]
            require(segment.text is not None, f"{name}: not a non-null display string")
            require(isinstance(replacement, Replacement), "replacement must be a Replacement value")
            require(isinstance(replacement.expected, bytes) and isinstance(replacement.value, bytes), "replacement values must be bytes")
            require(segment.text == replacement.expected, f"{name}: expected source bytes mismatch")
            require(b"\0" not in replacement.value, f"{name}: embedded NUL")
            require(bool(replacement.value) or not segment.text, f"{name}: unexpected empty replacement")
            control_view = replacement.value
            if glyph_marker is not None:
                require(glyph_marker.prefix not in segment.text, "approved glyph prefix collides with original control bytes")
                control_view = glyph_marker.control_view(control_view)
            require(protected_tokens(segment.text) == protected_tokens(control_view), f"{name}: protected token mismatch")
            require(segment.field_offset not in fields or fields[segment.field_offset] == replacement.value, "conflicting shared pointer replacements")
            fields[segment.field_offset] = replacement.value
        for segment in self.segments.values():
            if segment.field_offset in fields and fields[segment.field_offset] != segment.text:
                require(segment.id in replacements, "shared pointer field requires all affected IDs")
        out = bytearray(self.data)
        for field, value in sorted(fields.items()):
            source = next(s for s in self.segments.values() if s.field_offset == field)
            if source.text == value:
                continue
            require(len(out) + len(value) + 1 <= 0xFFFFFFFF, "rebuilt PDA exceeds u32 size")
            struct.pack_into("<I", out, field, len(out))
            out.extend(value + b"\0")
        result = bytes(out)
        verified = PdaResource(result)
        require(self.identifiers == verified.identifiers and self.index_values == verified.index_values, "non-text tables changed")
        for name, original in self.segments.items():
            expected = replacements[name].value if name in replacements else original.text
            require(verified.segments[name].text == expected, f"{name}: rebuilt text mismatch")
        return result

    def replace(self, replacements: Mapping[str, Replacement], *, glyph_marker: int | GlyphMarker | None = None, expected_sha256: str | None = None) -> bytes:
        """Convenience API for a builder that separately pins its source version.

        Each replacement still requires exact original bytes. An integer marker
        explicitly approves prefix + four decimal digits (IDs 0..9999); pass a
        GlyphMarker to constrain this further to the actual atlas size.
        """
        if type(glyph_marker) is int:
            require(0 < glyph_marker < 32, "glyph marker byte must be 1..31")
            glyph_marker = GlyphMarker(bytes([glyph_marker]), 4, 9999)
        require(glyph_marker is None or isinstance(glyph_marker, GlyphMarker), "invalid glyph marker contract")
        return self.rebuild(replacements, expected_sha256=expected_sha256 or sha256(self.data), glyph_marker=glyph_marker)

    def report(self) -> dict:
        return {
            "format": "second-sight-pda-v1",
            "source_sha256": sha256(self.data),
            "source_size": len(self.data),
            "pages": self.page_count,
            "images": self.image_count,
            "identifier_count": len(self.identifiers),
            "display_segment_count": sum(s.text is not None for s in self.segments.values()),
            "segments": [
                {"id": s.id, "pointer_field_offset": s.field_offset, "value": s.value,
                 "tag": s.tag, "row_metadata": s.row_metadata,
                 "source_hex": None if s.text is None else s.text.hex()}
                for s in self.segments.values()
            ],
        }


def rebuild_manifest(data: bytes, manifest: dict) -> bytes:
    require(isinstance(manifest, dict), "replacement manifest must be an object")
    require(manifest.get("format") == "second-sight-pda-replacements-v1", "unsupported replacement manifest")
    source_sha = manifest.get("source_sha256")
    require(isinstance(source_sha, str) and re.fullmatch(r"[0-9a-fA-F]{64}", source_sha) is not None, "invalid source SHA-256")
    records = manifest.get("replacements")
    require(isinstance(records, list), "replacements must be a list")
    replacements = {}
    for entry in records:
        require(isinstance(entry, dict), "replacement must be an object")
        name = entry.get("id")
        require(isinstance(name, str) and name not in replacements, "missing or duplicate replacement ID")
        for key in ("expected_hex", "replacement_hex"):
            require(isinstance(entry.get(key), str), f"{name}: {key} must be a hex string")
        replacements[name] = Replacement(bytes.fromhex(entry["expected_hex"]), bytes.fromhex(entry["replacement_hex"]))
    marker = None
    if "glyph_marker" in manifest:
        spec = manifest["glyph_marker"]
        require(isinstance(spec, dict) and isinstance(spec.get("prefix_hex"), str), "invalid glyph marker declaration")
        marker = GlyphMarker(bytes.fromhex(spec["prefix_hex"]), spec.get("digits"), spec.get("max_id"))
    return PdaResource(data).rebuild(replacements, expected_sha256=source_sha, glyph_marker=marker)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("source", type=Path)
    inspect.add_argument("--output", type=Path)
    rebuild = sub.add_parser("rebuild")
    rebuild.add_argument("source", type=Path)
    rebuild.add_argument("manifest", type=Path)
    rebuild.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        data = args.source.read_bytes()
        if args.command == "inspect":
            report = json.dumps(PdaResource(data).report(), indent=2) + "\n"
            if args.output:
                with args.output.open("x", encoding="utf-8", newline="\n") as output:
                    output.write(report)
            else:
                print(report, end="")
        else:
            require(args.source.resolve() != args.output.resolve(), "output must differ from source")
            require(args.manifest.resolve() != args.output.resolve(), "output must differ from manifest")
            result = rebuild_manifest(data, json.loads(args.manifest.read_text(encoding="utf-8")))
            with args.output.open("xb") as output:
                output.write(result)
            require(args.output.read_bytes() == result, "written output verification failed")
            print(f"PASS bytes={len(result)} sha256={sha256(result)}")
    except (ValueError, OSError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()
