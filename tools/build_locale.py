"""Build a small, locale-neutral runtime pack. Never installs or runs the game."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path
import struct

from assess_resources import Pak, StringTable, require
from pda_resources import PdaResource, Replacement, GlyphMarker
from translation_checks import check_locale
from font_dependencies import read_config, dependency, notice

ROOT = Path(__file__).resolve().parents[1]
EXE_SHA = "4092a8d1fb042dffe9fb95e2185f32cb80390299145e8d453a5e909a06d35fda"
BS_SHA = "e72b56066e8b68fb23ac2833b58376a18a506503e02e83864727eef1fbc03a7d"
PDA_SHA = "f684ffe987026172b5a69f82e11ee6426190bf629939596cad3f6571b098f6d7"
MARKER = 0x1f


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encode(text: str, glyphs: dict[str, int]) -> bytes:
    """All visible characters use tokens: adjacent ASCII digits cannot be swallowed."""
    out = bytearray()
    for char in text:
        if char in " \t\n":
            out.extend(char.encode("ascii"))
        else:
            require(ord(char) >= 32 and char != "\x7f", "unsupported control code in PoC")
            value = glyphs[char]
            require(0 <= value < 1536, "glyph exceeds six native pages")
            out.extend(bytes([MARKER]) + f"{value:04d}".encode("ascii"))
    return bytes(out)


def decode(data: bytes, glyphs: dict[str, int]) -> str:
    reverse = {value: char for char, value in glyphs.items()}
    result, i = [], 0
    while i < len(data):
        if data[i] in (9, 10, 32):
            result.append(chr(data[i])); i += 1
        else:
            require(data[i] == MARKER and len(data[i+1:i+5]) == 4 and data[i+1:i+5].isdigit(), "invalid glyph token")
            require(i+5 == len(data) or not 48 <= data[i+5] <= 57, "greedy native parser would consume extra digit")
            result.append(reverse[int(data[i+1:i+5])]); i += 5
    return "".join(result)


def dxt3(alpha) -> bytes:
    """BC2/DXT3: constant white RGB endpoints, explicit 4-bit coverage."""
    width, height = alpha.size
    require(width == height == 256, "native PoC atlas is 256 square")
    header = [124, 0x81007, height, width, width*height, 0, 1] + [0]*11
    header += [32, 4, struct.unpack("<I", b"DXT3")[0], 0, 0, 0, 0, 0]
    header += [0x1000, 0, 0, 0, 0]
    out = bytearray(b"DDS " + struct.pack("<31I", *header))
    for y in range(0, height, 4):
        for x in range(0, width, 4):
            bits = sum(((alpha.getpixel((x+dx, y+dy))*15+127)//255) << (4*(dy*4+dx))
                       for dy in range(4) for dx in range(4))
            out.extend(struct.pack("<QHHI", bits, 0xffff, 0xffff, 0))
    return bytes(out)


def make_atlases(glyphs: dict[str, int], font_path: Path, preview: Path) -> list[bytes]:
    from PIL import Image, ImageDraw, ImageFont
    from fontTools.ttLib import TTFont
    with TTFont(font_path) as font:
        cmap = font.getBestCmap()
        require(all(ord(c) in cmap for c in glyphs), "font lacks requested glyph")
    # Supersampling produces deterministic 16px cell coverage with 1px padding.
    font = ImageFont.truetype(str(font_path), 14*4)
    pages = [Image.new("L", (256, 256)) for _ in range(6)]
    for char, index in glyphs.items():
        tile = Image.new("L", (64, 64))
        draw = ImageDraw.Draw(tile)
        left, top, right, bottom = draw.textbbox((0, 0), char, font=font)
        require(right-left <= 60 and bottom-top <= 60, f"glyph cell overflow: {char}")
        draw.text(((64-(right-left))//2-left, (64-(bottom-top))//2-top), char, font=font, fill=255)
        pages[index//256].paste(tile.resize((16,16), Image.Resampling.LANCZOS), ((index%16)*16, ((index%256)//16)*16))
    pages[0].save(preview)
    return [dxt3(page) for page in pages]


def blob(value: bytes) -> bytes:
    return struct.pack("<I", len(value)) + value


def build(game: Path, locale: str, out: Path) -> dict:
    require(re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*",locale) is not None,"invalid locale identifier")
    require(not out.resolve().is_relative_to(game.resolve()),"output must be outside original game")
    require(digest((game/"secondsight.exe").read_bytes()) == EXE_SHA, "unsupported executable")
    data = json.loads((ROOT/"locales"/locale/"poc.json").read_text(encoding="utf-8"))
    require(data["locale"] == locale and data["schema"] == 1, "locale schema mismatch")
    editorial_errors=check_locale(ROOT/"locales"/locale,data)
    require(not editorial_errors,"editorial checks failed: "+"; ".join(editorial_errors))
    font_config=read_config(ROOT/"locales"/locale/"font.json")
    require(font_config['locale']==locale,"font locale mismatch")
    source = Pak((game/"pak/arcade/l_103.pak").read_bytes()).member("data/strsspxe.bs")
    require(digest(source) == BS_SHA, "unsupported BS input")
    table = StringTable(source)
    require(all(bytes([MARKER]) not in text for text in table.strings),"glyph marker collides with original BS")
    # Find one PDA mirror deterministically and verify all matching copies before using it.
    pda_sources = []
    for archive in sorted((game/"pak").rglob("*.pak")):
        pak = Pak(archive.read_bytes())
        if any(e["name"] == "data/pdaps_a.raw" for e in pak.entries):
            member = pak.member("data/pdaps_a.raw")
            require(digest(member) == PDA_SHA, f"unsupported PDA mirror: {archive}")
            pda_sources.append(member)
    require(bool(pda_sources), "PDA source not found")
    pda = PdaResource(pda_sources[0])
    require(all(s.text is None or bytes([MARKER]) not in s.text for s in pda.segments.values()),"glyph marker collides with original PDA")
    targets = data["bs"] + data["pda"]
    require(len({r["id"] for r in data["bs"]}) == len(data["bs"]), "duplicate BS ID")
    require(len({r["id"] for r in data["pda"]}) == len(data["pda"]), "duplicate PDA ID")
    characters = sorted(set("".join(r["target"] for r in targets)) - set(" \t\n"))
    slots = [i for i in range(1536) if i not in (178,184)]
    require(0 < len(characters) <= len(slots), "atlas capacity exceeded")
    glyphs = dict(zip(characters,slots))
    bs_records, pda_records, pda_replacements = [], [], {}
    for row in targets:
        require(bool(row["target"]), "empty PoC target")
        # PoC deliberately excludes formatting/control codes until their display paths are tested.
        require(not any(ord(c)<32 for c in row["source"]+row["target"]), "PoC control codes require separate review")
        require("%" not in row["source"]+row["target"], "PoC placeholder requires separate review")
        encoded = encode(row["target"], glyphs)
        require(len(encoded) <= 450, "PoC text exceeds conservative native wrap workspace budget")
        require(decode(encoded, glyphs) == row["target"], "encoding roundtrip failed")
        expected = row["source"].encode("ascii")
        if isinstance(row["id"], int):
            require(len(encoded)<=255,"BS exceeds native UI byte-copy limit")
            require(0 < row["id"] < len(table.strings) and table.strings[row["id"]] == expected, f"BS source mismatch: {row['id']}")
            bs_records.append(struct.pack("<I", row["id"]) + blob(expected) + blob(encoded))
        else:
            require(pda.segments[row["id"]].text == expected, f"PDA source mismatch: {row['id']}")
            pda_replacements[row["id"]] = Replacement(expected, encoded)
            pda_records.append(struct.pack("<I",pda.segments[row["id"]].field_offset)+blob(expected)+blob(encoded))
    out.mkdir(parents=True, exist_ok=True)
    font = dependency(ROOT/"build/dependencies",font_config['font'])
    license_file = dependency(ROOT/"build/dependencies",font_config['license'])
    atlas = make_atlases(glyphs, font, out/"atlas-preview.png")
    # The approved transport marker is removed only for protected-token comparison.
    rebuilt = pda.replace(pda_replacements, glyph_marker=GlyphMarker(bytes([MARKER]),4,1535))
    (out/"BASELINE.raw").write_bytes(pda.data)
    (out/"MODIFIED_FILE.raw").write_bytes(rebuilt)
    resources = [(f"textures/localization/page{i}.dds", payload) for i,payload in enumerate(atlas)]
    packed = b"SLP1" + struct.pack("<III",len(bs_records),len(pda_records),len(resources)) + b"".join(bs_records) + b"".join(pda_records)
    packed += b"".join(blob(name.encode("ascii"))+blob(payload) for name,payload in resources)
    (out/"locale.bin").write_bytes(packed)
    (out/"OFL.txt").write_bytes(license_file.read_bytes())
    (out/"FONT-NOTICE.txt").write_text(notice(font_config),encoding="utf-8",newline="\n")
    manifest = dict(schema=1, locale=locale, status="offline-built; user-runtime-acceptance-pending",
                    executable_sha256=EXE_SHA, bs_source_sha256=BS_SHA, pda_source_sha256=PDA_SHA,
                    font_commit=font_config['commit'],font_sha256=font_config['font']['sha256'],
                    font_family=font_config['family'],font_style=font_config['style'],font_version=font_config['version'],
                    editorial_inputs={name:digest((ROOT/"locales"/locale/name).read_bytes()) for name in ('poc.json','style.json','glossary.json','font.json')},glyphs=glyphs,
                    bs_ids=[r["id"] for r in data["bs"]], pda_ids=list(pda_replacements),
                    pack_sha256=digest(packed), pda_mirrors_checked=len(pda_sources),
                    resources=[dict(name=n,size=len(p),sha256=digest(p)) for n,p in resources])
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"LOCALE PASS: bs={len(bs_records)}; pda={len(pda_replacements)}; glyphs={len(glyphs)}; pages=6; runtime=PENDING")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-root",type=Path,required=True)
    parser.add_argument("--locale",default="zh-CN")
    parser.add_argument("--out",type=Path,required=True)
    args = parser.parse_args()
    build(args.game_root,args.locale,args.out)
