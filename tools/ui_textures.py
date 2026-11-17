"""Generate source-bound UI lettering from locale data, never from edited game art."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import struct
from assess_resources import require

ROOT = Path(__file__).resolve().parents[1]


def load(directory: Path) -> list[dict]:
    catalog = json.loads((directory/'poc.json').read_text(encoding='utf-8'))
    name = catalog.get('ui_textures')
    if name is None:
        return []
    require(name == 'ui-textures.json', 'unknown UI texture catalog')
    config = json.loads((directory/name).read_text(encoding='utf-8'))
    require(config['schema'] == 1 and config['locale'] == catalog['locale'], 'UI locale mismatch')
    contracts = json.loads((ROOT/'assets/ui-texture-contracts.json').read_text(encoding='utf-8'))
    indexed = {r['name']:r for r in contracts['resources']}
    rows = config['resources']
    require(len({r['name'] for r in rows}) == len(rows), 'duplicate UI texture')
    result = []
    for row in rows:
        require(row['name'] in indexed, 'unaudited UI resource')
        require(isinstance(row['lines'], list) and 0 < len(row['lines']) <= 4, 'invalid UI lines')
        for line in row['lines']:
            text = line['text']
            require(isinstance(text,str) and text and all(ord(c)>=32 for c in text), 'invalid UI text')
            require(type(line['size']) is int and 1<=line['size']<=64, 'invalid UI font size')
            require(type(line['center_y']) is int, 'invalid UI text position')
        result.append(dict(contract=indexed[row['name']], layout=row))
    return result


def validate_sources(rows: list[dict], sources: dict[str,list[bytes]]) -> None:
    for row in rows:
        c = row['contract']
        copies = sources.get(c['name'], [])
        require(len(copies) == c['mirror_count'], 'UI resource mirror count mismatch')
        require(all(len(b)==c['source_bytes'] and hashlib.sha256(b).hexdigest()==c['source_sha256'] for b in copies), 'UI source identity mismatch')


def dxt3_solid(alpha, rgb565: int) -> bytes:
    """Explicit 4-bit alpha with one RGB565 endpoint; no proprietary pixel data."""
    w,h = alpha.size
    require(alpha.mode=='L' and w%4==0 and h%4==0 and 0<w<=512 and 0<h<=512, 'invalid UI dimensions')
    require(type(rgb565) is int and 0<=rgb565<=65535, 'invalid UI color')
    header=[124,0x81007,h,w,w*h,0,1]+[0]*11
    header += [32,4,struct.unpack('<I',b'DXT3')[0],0,0,0,0,0]
    header += [0x1000,0,0,0,0]
    out=bytearray(b'DDS '+struct.pack('<31I',*header))
    for y in range(0,h,4):
        for x in range(0,w,4):
            bits=sum(((alpha.getpixel((x+dx,y+dy))*15+127)//255)<<(4*(dy*4+dx)) for dy in range(4) for dx in range(4))
            out.extend(struct.pack('<QHHI',bits,rgb565,rgb565,0))
    return bytes(out)


def render(row: dict, font_path: Path, preview: Path | None = None) -> bytes:
    from PIL import Image, ImageDraw, ImageFont
    from fontTools.ttLib import TTFont
    c,layout=row['contract'],row['layout']
    w,h=c['width'],c['height']
    with TTFont(font_path) as font:
        cmap=font.getBestCmap()
        require(all(ord(ch) in cmap for line in layout['lines'] for ch in line['text']), 'UI font lacks glyph')
    scale=4
    alpha=Image.new('L',(w*scale,h*scale))
    draw=ImageDraw.Draw(alpha)
    for line in layout['lines']:
        face=ImageFont.truetype(str(font_path),line['size']*scale)
        left,top,right,bottom=draw.textbbox((0,0),line['text'],font=face)
        tw,th=right-left,bottom-top
        x=(w*scale-tw)//2; y=line['center_y']*scale-th//2
        require(x>=0 and y>=0 and x+tw<=w*scale and y+th<=h*scale, 'UI text clips')
        draw.text((x-left,y-top),line['text'],font=face,fill=255)
    if 'frame' in layout:
        box=layout['frame']
        require(len(box)==4 and all(type(v) is int for v in box) and 0<=box[0]<box[2]<w and 0<=box[1]<box[3]<h, 'UI frame clips')
        draw.rectangle(tuple(v*scale for v in box),outline=255,width=scale)
    alpha=alpha.resize((w,h),Image.Resampling.LANCZOS)
    if preview:
        # Preview is upright on black. Stored DDS follows the original UV direction.
        color=c['rgb565']; rgb=(((color>>11)&31)*255//31,((color>>5)&63)*255//63,(color&31)*255//31)
        image=Image.new('RGBA',(w,h),rgb+(0,)); image.putalpha(alpha)
        bg=Image.new('RGBA',(w,h),'black'); bg.alpha_composite(image)
        bg.resize((w*4,h*4)).save(preview)
    if c['vertical_flip']:
        alpha=alpha.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    return dxt3_solid(alpha,c['rgb565'])
