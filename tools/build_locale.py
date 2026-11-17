"""Build a small, locale-neutral runtime pack. Never installs or runs the game."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path
import struct

from assess_resources import Pak, require
from pda_resources import PdaResource, Replacement, GlyphMarker
from translation_checks import check_locale
from font_dependencies import read_config, dependency, notice
from locale_catalog import load_catalog, bind_sources, catalog_files
from source_variants import load_tables, aliases_for, pack_aliases
from text_transport import parts, check_contract, expanded_budget, bs_limit, bs_expanded_limit, DEFERRED_BS_IDS, COMPOSED_BS_IDS, UNRESOLVED_BS_IDS
import ui_textures
import exe_texts

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
    for protected, char in parts(text):
        if protected or char == " ":
            out.extend(char.encode("ascii"))
        else:
            require(ord(char) >= 32 and char != "\x7f", "unsupported control code in PoC")
            value = glyphs[char]
            require(0 <= value < 6144, "glyph exceeds six native pages")
            out.extend(bytes([MARKER]) + f"{value:04d}".encode("ascii"))
    return bytes(out)


def decode(data: bytes, glyphs: dict[str, int]) -> str:
    reverse = {value: char for char, value in glyphs.items()}
    result, i = [], 0
    while i < len(data):
        if data[i] == 11 and i+1<len(data) and chr(data[i+1]) in '123456789ABCDEFGHIJK':
            result.append(data[i:i+2].decode('ascii')); i += 2
        elif data[i:i+1] == b'%' and i+1<len(data) and (49 <= data[i+1] <= 57 or data[i+1] == ord('s')):
            result.append(data[i:i+2].decode('ascii')); i += 2
        elif data[i] in (9, 10, 32):
            result.append(chr(data[i])); i += 1
        else:
            require(data[i] == MARKER and len(data[i+1:i+5]) == 4 and data[i+1:i+5].isdigit(), "invalid glyph token")
            require(i+5 == len(data) or not 48 <= data[i+5] <= 57, "greedy native parser would consume extra digit")
            result.append(reverse[int(data[i+1:i+5])]); i += 5
    return "".join(result)


def dxt3(alpha) -> bytes:
    """BC2/DXT3: constant white RGB endpoints, explicit 4-bit coverage."""
    width, height = alpha.size
    require(width == height and width in (512,1024), "unsupported font atlas dimensions")
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


ATLAS_CELL = 32
ATLAS_BASELINE = 24.5
ATLAS_EM = 27


def raster_glyph(char, font):
    from PIL import Image, ImageDraw
    side=ATLAS_CELL*4
    tile=Image.new("L",(side,side))
    left,top,right,bottom=font.getbbox(char,anchor="ls")
    baseline=int(ATLAS_BASELINE*4)
    require(right-left<=side-4 and baseline+top>=2 and baseline+bottom<=side-2,
            f"glyph cell overflow: {char}")
    # Horizontal cell alignment is preserved. Vertically lay out all glyphs
    # on the same font baseline, not at the centre of their ink bounds.
    ImageDraw.Draw(tile).text(((side-(right-left))//2-left,baseline),char,
                             font=font,fill=255,anchor="ls")
    tile=tile.resize((ATLAS_CELL,ATLAS_CELL),Image.Resampling.LANCZOS)
    # Reserve a fully transparent gutter, including filtering undershoot.
    tile.paste(0,(0,0,ATLAS_CELL,1))
    tile.paste(0,(0,ATLAS_CELL-1,ATLAS_CELL,ATLAS_CELL))
    tile.paste(0,(0,0,1,ATLAS_CELL))
    tile.paste(0,(ATLAS_CELL-1,0,ATLAS_CELL,ATLAS_CELL))
    require(tile.getbbox() is not None, f"empty glyph raster: {char}")
    return tile


def make_atlases(glyphs: dict[str, int], font_path: Path, preview: Path) -> list[bytes]:
    from PIL import Image, ImageFont
    from fontTools.ttLib import TTFont
    with TTFont(font_path) as font:
        cmap = font.getBestCmap()
        require(all(ord(c) in cmap for c in glyphs), "font lacks requested glyph")
    font = ImageFont.truetype(str(font_path), ATLAS_EM*4)
    side=32*ATLAS_CELL
    pages = [Image.new("L", (side, side)) for _ in range(6)]
    for char, index in glyphs.items():
        pages[index//1024].paste(raster_glyph(char,font),
                                ((index%32)*ATLAS_CELL, ((index%1024)//32)*ATLAS_CELL))
    pages[0].save(preview)
    return [dxt3(page) for page in pages]


def blob(value: bytes) -> bytes:
    return struct.pack("<I", len(value)) + value


def pack_runtime(bs_records: list[bytes], pda_records: list[bytes], exe_records: list[bytes],
                 resources: list[tuple[str, bytes]], aliases: dict[int, list[bytes]]) -> bytes:
    alias_count, alias_records = pack_aliases(aliases)
    # SLP3 retains SLP2 text records and adds source-only aliases before resources.
    packed = b'SLP3' + struct.pack('<IIIII', len(bs_records), len(pda_records), len(resources), len(exe_records), alias_count)
    packed += b''.join(bs_records) + b''.join(pda_records) + b''.join(exe_records) + alias_records
    return packed + b''.join(blob(name.encode('ascii')) + blob(payload) for name, payload in resources)


def build(game: Path, locale: str, out: Path) -> dict:
    require(re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*",locale) is not None,"invalid locale identifier")
    require(not out.resolve().is_relative_to(game.resolve()),"output must be outside original game")
    require(digest((game/"secondsight.exe").read_bytes()) == EXE_SHA, "unsupported executable")
    data = load_catalog(ROOT/"locales"/locale)
    require(data["locale"] == locale and data["schema"] == 1, "locale schema mismatch")
    editorial_errors=check_locale(ROOT/"locales"/locale,data)
    require(not editorial_errors,"editorial checks failed: "+"; ".join(editorial_errors))
    font_config=read_config(ROOT/"locales"/locale/"font.json")
    require(font_config['locale']==locale,"font locale mismatch")
    ui_rows=ui_textures.load(ROOT/'locales'/locale)
    ui_sources={r['contract']['name']:[] for r in ui_rows}
    variant_path = ROOT/'assets/source-variants.json'
    variant_profile = json.loads(variant_path.read_text(encoding='utf-8'))
    variant_tables = load_tables(game, variant_profile)
    table = variant_tables[variant_profile['primary']]
    primary_identity = next(source for source in variant_profile['sources'] if source['id'] == variant_profile['primary'])
    require(primary_identity['sha256'] == BS_SHA, 'primary BS catalog identity mismatch')
    require(all(bytes([MARKER]) not in text for variant in variant_tables.values() for text in variant.strings),
            "glyph marker collides with original BS")
    # Find one PDA mirror deterministically and verify all matching copies before using it.
    pda_sources = []
    for archive in sorted((game/"pak").rglob("*.pak")):
        pak = Pak(archive.read_bytes())
        for entry in pak.entries:
            if entry['name'] in ui_sources:
                ui_sources[entry['name']].append(pak.member(entry['name']))
        if any(e["name"] == "data/pdaps_a.raw" for e in pak.entries):
            member = pak.member("data/pdaps_a.raw")
            require(digest(member) == PDA_SHA, f"unsupported PDA mirror: {archive}")
            pda_sources.append(member)
    require(bool(pda_sources), "PDA source not found")
    ui_textures.validate_sources(ui_rows,ui_sources)
    pda = PdaResource(pda_sources[0])
    data = bind_sources(data, table.strings, {k:s.text for k,s in pda.segments.items() if s.text})
    source_aliases = aliases_for(data['bs'], variant_profile, variant_tables)
    data = exe_texts.bind(data,(game/'secondsight.EXE').read_bytes())
    coverage_report = None
    if data.get('coverage',{}).get('bs')=='complete_table_inventory':
        from audit_coverage import audit
        inventory=json.loads((ROOT/'locales'/locale/'coverage.json').read_text(encoding='utf-8'))
        coverage_report=audit(data,inventory,{str(i):s.decode('cp1252') for i,s in enumerate(table.strings)})
    editorial_errors=check_locale(ROOT/"locales"/locale,data)
    require(not editorial_errors,"bound editorial checks failed: "+"; ".join(editorial_errors))
    require(all(s.text is None or bytes([MARKER]) not in s.text for s in pda.segments.values()),"glyph marker collides with original PDA")
    targets = data["bs"] + data["pda"] + data['exe']
    if data.get('coverage',{}).get('pda')=='all_nonempty_display_segments':
        require({r['id'] for r in data['pda']}=={k for k,s in pda.segments.items() if s.text}, 'PDA coverage incomplete')
    require(len({r["id"] for r in data["bs"]}) == len(data["bs"]), "duplicate BS ID")
    require(len({r["id"] for r in data["pda"]}) == len(data["pda"]), "duplicate PDA ID")
    characters = sorted({char for row in targets for protected,char in parts(row['target']) if not protected and char!=' '})
    slots = [i for i in range(6144) if i not in (178,184)]
    require(0 < len(characters) <= len(slots), "atlas capacity exceeded")
    glyphs = dict(zip(characters,slots))
    bs_records, pda_records, exe_records, pda_replacements = [], [], [], {}
    target_groups=[(group,row) for group in ('bs','pda','exe') for row in data[group]]
    for group,row in target_groups:
        require(bool(row["target"]), "empty PoC target")
        check_contract(row)
        encoded = encode(row["target"], glyphs)
        if group=='exe':
            require(len(encoded)<=64 and not any(protected for protected,_ in parts(row['target'])), 'hardcoded UI byte/control limit')
            require(decode(encoded,glyphs)==row['target'],'hardcoded UI roundtrip failed')
            exe_records.append(struct.pack('<I',row['id'])+blob(row['source'].encode('ascii'))+blob(encoded))
            continue
        require(expanded_budget(encoded, identifier=row["id"] if isinstance(row["id"],int) else None) <= (bs_expanded_limit(row['id']) if isinstance(row['id'],int) else 1800), f"{row['id']}: expanded consumer budget exceeded")
        if row['id'] in (601,5224):
            require(len(encoded)<=10, 'hold/press label exceeds inspected tutorial template budget')
        if isinstance(row['id'],int) and 6371<=row['id']<=6504:
            require(len(encoded)<=27, f"{row['id']}: native dual-key 64-byte formatter budget exceeded")
        if isinstance(row['id'],int) and row['id'] in (6518,6519):
            require(len(encoded)<=27, 'movement/mouse name exceeds control expansion budget')
        require(decode(encoded, glyphs) == row["target"], "encoding roundtrip failed")
        expected = row["source"].encode("cp1252")
        if isinstance(row["id"], int):
            require(len(encoded)<=bs_limit(row["id"]),f"{row['id']}: BS exceeds verified consumer byte-copy limit")
            require(0 < row["id"] < len(table.strings) and table.strings[row["id"]] == expected, f"BS source mismatch: {row['id']}")
            bs_records.append(struct.pack("<I", row["id"]) + blob(expected) + blob(encoded))
        else:
            require(pda.segments[row["id"]].text == expected, f"PDA source mismatch: {row['id']}")
            pda_replacements[row["id"]] = Replacement(expected, encoded)
            pda_records.append(struct.pack("<I",pda.segments[row["id"]].field_offset)+blob(expected)+blob(encoded))
    composed=[r for r in data['bs'] if r['id'] in COMPOSED_BS_IDS]
    if composed:
        require({r['id'] for r in composed}==COMPOSED_BS_IDS,'terminal composition needs all five source-bound paragraphs')
        require(sum(len(encode(r['target'],glyphs)) for r in composed)+8<=4095,'terminal combined target exceeds owned budget')
    out.mkdir(parents=True, exist_ok=True)
    font = dependency(ROOT/"build/dependencies",font_config['font'])
    license_file = dependency(ROOT/"build/dependencies",font_config['license'])
    atlas = make_atlases(glyphs, font, out/"atlas-preview.png")
    # The approved transport marker is removed only for protected-token comparison.
    rebuilt = pda.replace(pda_replacements, glyph_marker=GlyphMarker(bytes([MARKER]),4,6143))
    (out/"BASELINE.raw").write_bytes(pda.data)
    (out/"MODIFIED_FILE.raw").write_bytes(rebuilt)
    resources = [(f"textures/localization/page{i}.dds", payload) for i,payload in enumerate(atlas)]
    for i,row in enumerate(ui_rows):
        resources.append((row['contract']['name'],ui_textures.render(row,font,out/f'ui-preview-{i}.png')))
    packed = pack_runtime(bs_records, pda_records, exe_records, resources, source_aliases)
    (out/"locale.bin").write_bytes(packed)
    (out/"OFL.txt").write_bytes(license_file.read_bytes())
    (out/"FONT-NOTICE.txt").write_text(notice(font_config),encoding="utf-8",newline="\n")
    manifest = dict(schema=1, locale=locale, status="offline-built; user-runtime-acceptance-pending",
                    executable_sha256=EXE_SHA, bs_source_sha256=BS_SHA, pda_source_sha256=PDA_SHA,
                    font_commit=font_config['commit'],font_sha256=font_config['font']['sha256'],
                    font_family=font_config['family'],font_style=font_config['style'],font_version=font_config['version'],
                    editorial_inputs={name:digest((ROOT/"locales"/locale/name).read_bytes()) for name in catalog_files(ROOT/"locales"/locale)},glyphs=glyphs,
                    targets={group:{str(r['id']):r['target'] for r in data[group]} for group in ('bs','pda','exe')},
                    coverage=dict(pda_selected=len(data['pda']),pda_available=sum(bool(s.text) for s in pda.segments.values()),
                                  pda_pages=len({s.page for s in pda.segments.values() if s.text}),
                                  bs_selected=len(data['bs']),bs_available=len(table.strings)),
                    bs_ids=[r["id"] for r in data["bs"]], pda_ids=list(pda_replacements),
                    pack_sha256=digest(packed), pda_mirrors_checked=len(pda_sources),
                    resources=[dict(name=n,size=len(p),sha256=digest(p)) for n,p in resources])
    if coverage_report is not None:
        manifest['complete_inventory']=coverage_report
    manifest['bs_binding']=dict(direct_ids=[r['id'] for r in data['bs'] if r['id'] not in DEFERRED_BS_IDS],
                                deferred_ids=[r['id'] for r in data['bs'] if r['id'] in DEFERRED_BS_IDS],
                                unresolved_ids=sorted(UNRESOLVED_BS_IDS & {r['id'] for r in data['bs']}),
                                composed_ids=sorted(COMPOSED_BS_IDS & {r['id'] for r in data['bs']}),
                                deferred_status='complete target retained; original BS pointer preserved; only audited long-wrap callers may substitute; unobserved consumers pending')
    manifest['atlas_layout']=dict(page_count=6,width=32*ATLAS_CELL,height=32*ATLAS_CELL,
                                  cell=ATLAS_CELL,em=ATLAS_EM,baseline=ATLAS_BASELINE,
                                  glyph_slots=6144,reserved_ids=[178,184])
    manifest['pack_format']='SLP3'
    manifest['source_variants']=dict(profile_sha256=digest(variant_path.read_bytes()),
                                    primary=variant_profile['primary'],table_slots=variant_profile['table_slots'],
                                    sources=variant_profile['sources'],alias_count=sum(map(len,source_aliases.values())),
                                    bs_aliases={str(identifier):[digest(value) for value in values]
                                                for identifier,values in sorted(source_aliases.items())},
                                    matching='exact source bytes at identical BS ID; shared target; no fuzzy matching')
    manifest['exe_text_ids']=[r['id'] for r in data['exe']]
    manifest['exe_text_contracts_sha256']=digest((ROOT/'assets/exe-text-contracts.json').read_bytes())
    manifest['ui_textures']=[dict(name=r['contract']['name'],source_sha256=r['contract']['source_sha256'],
                                mirrors_checked=len(ui_sources[r['contract']['name']]),
                                lines=[line['text'] for line in r['layout']['lines']]) for r in ui_rows]
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
