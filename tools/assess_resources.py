"""Offline P4CK/BS assessment; never installs or launches game files.

P4CK layout independently checked against the supplied game and the legacy
PAK_P4CK.bms listed at https://mirror.aluigi.org/quickbms_list.php?folder=xentax_cs.
This implementation is original Python, not a port of that script.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


class Pak:
    def __init__(self, data: bytes):
        require(len(data) >= 16, "truncated P4CK header")
        magic, self.toc, self.table_size, names_size = struct.unpack_from("<4sIII", data)
        require(magic == b"P4CK", "wrong P4CK magic")
        require(self.toc >= 16 and self.table_size % 16 == 0, "invalid directory")
        require(self.toc + self.table_size + names_size == len(data), "directory bounds mismatch")
        self.data = data
        self.entries = []
        for i in range(self.table_size // 16):
            name_off, offset, size, unknown = struct.unpack_from("<4I", data, self.toc + i * 16)
            require(self.table_size <= name_off < self.table_size + names_size, "invalid name offset")
            end = data.find(b"\0", self.toc + name_off)
            require(end >= 0, "unterminated member name")
            name = data[self.toc + name_off:end].decode("ascii")
            require(bool(name), "empty member name")
            require(16 <= offset <= offset + size <= self.toc, "member outside data region")
            self.entries.append(dict(name=name, offset=offset, size=size, unknown=unknown, index=i))

    def member(self, name: str) -> bytes:
        entries = [e for e in self.entries if e["name"] == name]
        if not entries:
            raise KeyError(name)
        require(len(entries) == 1, "ambiguous duplicate member name; select by entry index instead")
        entry = entries[0]
        return self.data[entry["offset"]:entry["offset"] + entry["size"]]

    def replace(self, name: str, payload: bytes, alignment: int = 2048) -> bytes:
        """Append-and-repoint experiment. Preserve all other member offsets/data.

        Alignment is explicit; 2048 is conservative for this tested arcade PAK.
        This is a structural experiment, not proof of runtime archive acceptance.
        """
        original = self.member(name)
        if original == payload:
            return self.data
        require(alignment > 0 and alignment & (alignment - 1) == 0, "alignment must be a power of two")
        require(all(e["unknown"] == 0 for e in self.entries), "unrecognized directory flags")
        offset = (self.toc + alignment - 1) & -alignment
        new_toc = (offset + len(payload) + 15) & -16
        require(new_toc + len(self.data) - self.toc <= 0xFFFFFFFF, "archive exceeds u32 bounds")
        out = bytearray(self.data[:self.toc])
        out.extend(bytes(offset - len(out)))
        out.extend(payload)
        out.extend(bytes(new_toc - len(out)))
        out.extend(self.data[self.toc:])
        struct.pack_into("<I", out, 4, new_toc)
        entry = next(e for e in self.entries if e["name"] == name)
        struct.pack_into("<II", out, new_toc + entry["index"] * 16 + 4, offset, len(payload))
        result = bytes(out)
        Pak(result)
        return result


class StringTable:
    def __init__(self, data: bytes):
        require(len(data) >= 4, "truncated BS table")
        first = struct.unpack_from("<I", data)[0]
        require(4 <= first < len(data) and first % 4 == 0, "invalid BS pointer table")
        self.data = data
        self.offsets = struct.unpack_from(f"<{first // 4}I", data)
        self.strings = []
        for offset in self.offsets:
            require(first <= offset < len(data), "BS offset outside string pool")
            end = data.find(b"\0", offset)
            require(end >= 0, "unterminated BS string")
            self.strings.append(data[offset:end])

    def replace(self, index: int, payload: bytes) -> bytes:
        require(0 <= index < len(self.strings), "BS ID outside table")
        require(b"\0" not in payload, "embedded terminator")
        if payload == self.strings[index]:
            return self.data
        require(index != 0, "ID 0 anchors the inferred table size; this assessment probe preserves it")
        require(len(self.data) + len(payload) + 1 <= 0xFFFFFFFF, "BS exceeds u32 bounds")
        result = bytearray(self.data)
        struct.pack_into("<I", result, index * 4, len(result))
        result.extend(payload + b"\0")
        return bytes(result)


MEMBER = "data/strsspxe.bs"
PROBE_ID = 850
PROBE_VALUE = b"Localization probe"
EXPECTED = "e72b56066e8b68fb23ac2833b58376a18a506503e02e83864727eef1fbc03a7d"


def prepare(game: Path, out: Path) -> None:
    require(not (out / "probe.json").exists(), "probe already exists; choose a new output directory")
    source = game / "pak/arcade/l_103.pak"
    raw = source.read_bytes()
    pak = Pak(raw)
    table_data = pak.member(MEMBER)
    require(sha(table_data) == EXPECTED, "source BS identity mismatch")
    table = StringTable(table_data)
    require(len(table.strings) == 6526 and table.strings[PROBE_ID] == b"New Game", "unexpected source table")
    modified = pak.replace(MEMBER, table.replace(PROBE_ID, PROBE_VALUE))
    out.mkdir(parents=True, exist_ok=True)
    (out / "BASELINE.pak").write_bytes(raw)
    (out / "MODIFIED_FILE.pak").write_bytes(modified)
    manifest = dict(source=str(source.resolve()), baseline_sha256=sha(raw), modified_sha256=sha(modified),
                    member=MEMBER, id=PROBE_ID, original="New Game", modified=PROBE_VALUE.decode("ascii"),
                    scope="offline structural probe; not installed; no runtime rendering claim")
    (out / "probe.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    diff = dict(manifest, changed_fields=["P4CK header directory offset", "target member data offset and size", "BS pointer[850]", "appended ASCII string"],
                original_bs_sha256=sha(table_data), modified_bs_sha256=sha(Pak(modified).member(MEMBER)),
                original_size=len(raw), modified_size=len(modified), preserved_other_members=len(pak.entries)-1)
    (out / "DIFF_FILE.json").write_text(json.dumps(diff, indent=2), encoding="utf-8")
    script = Path(__file__).resolve().as_posix()
    rollback = '#!/usr/bin/env bash\nset -euo pipefail\nHERE="$(cd -- "$(dirname -- "$0")" && pwd)"\n'
    rollback += 'if [ "$#" -ne 1 ]; then echo "Usage: ROLLBACK.sh TARGET_COPY" >&2; exit 2; fi\n'
    rollback += f'exec python "{script}" restore "$HERE" --target "$1"\n'
    (out / "ROLLBACK.sh").write_text(rollback, encoding="utf-8", newline="\n")
    (out / "ROLLBACK.sh").chmod(0o755)
    print("PREPARE PASS: isolated modified archive created; installed source unchanged")


def check(stage: str, out: Path) -> None:
    manifest = json.loads((out / "probe.json").read_text(encoding="utf-8"))
    original = (out / "BASELINE.pak").read_bytes()
    require(sha(original) == manifest["baseline_sha256"], "baseline hash mismatch")
    require(sha(Path(manifest["source"]).read_bytes()) == sha(original), "installed source changed")
    baseline = Pak(original)
    if stage == "baseline":
        table = StringTable(baseline.member(MEMBER))
        require(baseline.replace(MEMBER, table.replace(PROBE_ID, b"New Game")) == original, "identity roundtrip mismatch")
        print('BASELINE PASS: entries=6526; id=850; value="New Game"; roundtrip=byte-identical')
    elif stage == "modified":
        modified = (out / "MODIFIED_FILE.pak").read_bytes()
        require(sha(modified) == manifest["modified_sha256"], "modified hash mismatch")
        pak = Pak(modified)
        a, b = StringTable(baseline.member(MEMBER)), StringTable(pak.member(MEMBER))
        require(len(a.strings) == len(b.strings), "entry count changed")
        require([i for i, (x, y) in enumerate(zip(a.strings, b.strings)) if x != y] == [PROBE_ID], "unexpected changed ID")
        require(b.strings[PROBE_ID] == PROBE_VALUE, "probe text mismatch")
        require([e["name"] for e in pak.entries] == [e["name"] for e in baseline.entries], "member ordering changed")
        require(all(baseline.member(e["name"]) == pak.member(e["name"]) for e in pak.entries if e["name"] != MEMBER), "unrelated member changed")
        print('MODIFIED PASS: id=850; value="Localization probe"; other_ids=6525 unchanged; other_members=6 unchanged')
    elif stage == "rollback":
        restored = (out / "ROLLBACK_TEST.pak").read_bytes()
        require(restored == original, "rollback is not byte-identical")
        require(sha((out / "MODIFIED_FILE.pak").read_bytes()) == manifest["modified_sha256"], "modified deliverable changed")
        print('ROLLBACK PASS: copy=byte-identical; id=850; value="New Game"; modified_artifact=retained')


def restore(out: Path, target: Path) -> None:
    manifest = json.loads((out / "probe.json").read_text(encoding="utf-8"))
    target = target.resolve()
    require(target.parent == out.resolve() and target.name == "ROLLBACK_TEST.pak", "rollback target must be the designated isolated test copy")
    require(sha(target.read_bytes()) == manifest["modified_sha256"], "rollback target identity mismatch")
    original = (out / "BASELINE.pak").read_bytes()
    require(sha(original) == manifest["baseline_sha256"], "rollback source identity mismatch")
    target.write_bytes(original)
    require(sha(target.read_bytes()) == manifest["baseline_sha256"], "restore verification failed")
    print('RESTORE PASS: target=ROLLBACK_TEST.pak; baseline SHA-256 restored')


def inventory(game: Path, out: Path) -> None:
    archives, rows, text_resources = [], [], []
    for path in sorted(game.rglob("*.pak")):
        raw = path.read_bytes()
        pak = Pak(raw)
        relative = path.relative_to(game).as_posix()
        archives.append(dict(path=relative, size=len(raw), sha256=sha(raw), members=len(pak.entries)))
        for entry in pak.entries:
            rows.append(dict(archive=relative, **entry))
            if entry["name"].endswith(".bs") or entry["name"].startswith("data/pdaps_"):
                payload = raw[entry["offset"]:entry["offset"] + entry["size"]]
                info = dict(archive=relative, name=entry["name"], size=len(payload), sha256=sha(payload))
                if entry["name"].endswith(".bs"):
                    table = StringTable(payload)
                    unique = set(table.strings)
                    info.update(ids=len(table.strings), nonempty_ids=sum(bool(x) for x in table.strings),
                                unique_strings=len(unique), unique_nonempty=sum(bool(x) for x in unique),
                                unique_word_tokens=sum(len(re.findall(rb"[A-Za-z]+(?:'[A-Za-z]+)?", s)) for s in unique),
                                control_byte_counts=dict(Counter(c for s in unique for c in s if c < 32)))
                text_resources.append(info)
    exe = game / "secondsight.EXE"
    report = dict(game_root=str(game.resolve()), executable_sha256=sha(exe.read_bytes()),
                  archives=archives, archive_count=len(archives), member_count=len(rows),
                  unique_member_names=len({r["name"] for r in rows}), text_resources=text_resources,
                  limitations=["archive boundary checks are not a game-load test", "word tokens are not finalized translation workload", "PDA parser and glyph rendering not verified here"])
    out.mkdir(parents=True, exist_ok=True)
    (out / "inventory.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out / "pak_inventory.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f'INVENTORY PASS: archives={len(archives)}; members={len(rows)}; unique_names={report["unique_member_names"]}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["inventory", "prepare", "baseline", "modified", "rollback", "restore"])
    parser.add_argument("output", type=Path)
    parser.add_argument("--game-root", type=Path)
    parser.add_argument("--target", type=Path)
    args = parser.parse_args()
    if args.action in ("inventory", "prepare"):
        require(args.game_root is not None, "--game-root is required")
        (inventory if args.action == "inventory" else prepare)(args.game_root, args.output)
    elif args.action == "restore":
        require(args.target is not None, "--target is required")
        restore(args.output, args.target)
    else:
        check(args.action, args.output)


if __name__ == "__main__":
    main()
