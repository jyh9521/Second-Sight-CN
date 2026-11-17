"""Check final packed DDS pixels and native x86 UV arithmetic without the game."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import struct

from PIL import Image
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_ESP

from inspect_renderer import EXPECTED_SHA256, PATCH_SITES

UV_SITES = tuple((a, bytes.fromhex(before)) for name,(a,before) in PATCH_SITES.items()
                 if name.startswith('hd_atlas_'))


def check_uv(exe, cell):
    raw=exe.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=EXPECTED_SHA256: raise ValueError('EXE identity')
    pe=pefile.PE(data=raw)
    u=Uc(UC_ARCH_X86,UC_MODE_32)
    base=0x400000
    u.mem_map(base,(pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095)
    u.mem_write(base,pe.get_memory_mapped_image())
    scratch=0x24000000
    u.mem_map(scratch,0x2000)
    shift=cell.bit_length()-1
    encoded=(bytes([0xc1,0xe0,shift]),bytes([0x8d,0x50,cell-1]),
             bytes([0xc1,0xe1,shift]),b'\x81\xc2'+struct.pack('<I',(cell-1)*16))
    for (address,before),after in zip(UV_SITES,encoded,strict=True):
        if bytes(u.mem_read(address,len(before)))!=before: raise ValueError('UV original bytes')
        if cell>16: u.mem_write(address,after)
    # The real x86 coordinate builder runs up to the indirect draw call.
    # Caller-supplied geometry is deliberately unchanged between modes.
    for col,row in ((0,0),(1,7),(31,31)):
        stk=scratch+0x1000
        u.mem_write(stk-0x40,bytes(0x140))
        u.reg_write(UC_X86_REG_ESP,stk)
        u.reg_write(UC_X86_REG_EAX,row)
        u.reg_write(UC_X86_REG_ECX,col)
        u.emu_start(0x612603,0x61264C,count=40)
        sp=u.reg_read(UC_X86_REG_ESP)
        left,top,right,bottom=struct.unpack('<4I',u.mem_read(sp+16,16))
        pad_right,pad_bottom=((cell-1)*16,)*2 if cell>16 else (248,256)
        wanted=(col*cell*16,row*cell*16,col*cell*16+pad_right,row*cell*16+pad_bottom)
        if (left,top,right,bottom)!=wanted: raise ValueError('wrong native UV arithmetic')
        if cell>16 and max(right,bottom)+8>=32*cell*16: raise ValueError('UV escaped page')
    return 3


def check_font(locale, manifest, phrase, preview=None):
    raw=locale.read_bytes()
    metadata=json.loads(manifest.read_text(encoding='utf-8'))
    if hashlib.sha256(raw).hexdigest()!=metadata['pack_sha256']: raise ValueError('pack hash')
    cell=metadata['atlas_layout']['cell']
    if cell not in (16,32,64): raise ValueError('cell')
    atlases=[]
    for page,row in enumerate(metadata['resources'][:6]):
        name=f'textures/localization/page{page}.dds'
        if row['name']!=name: raise ValueError('atlas resource order')
        token=name.encode('ascii')
        offset=raw.index(struct.pack('<I',len(token))+token)+4+len(token)
        length=struct.unpack_from('<I',raw,offset)[0]
        dds=raw[offset+4:offset+4+length]
        if hashlib.sha256(dds).hexdigest()!=row['sha256']: raise ValueError('DDS hash')
        alpha=Image.open(io.BytesIO(dds)).convert('RGBA').getchannel('A')
        if alpha.size!=(32*cell,32*cell): raise ValueError('DDS dimensions')
        atlases.append(alpha)

    def tile(char):
        idx=metadata['glyphs'][char]
        x=idx%32*cell
        y=(idx%1024//32)*cell
        return atlases[idx//1024].crop((x,y,x+cell,y+cell))

    boxes={c:tile(c).point(lambda a:255 if a>=85 else 0).getbbox() for c in '外。，、！？「」' if c in metadata['glyphs']}
    if not all(boxes.values()): raise ValueError('empty glyph')
    center=lambda c: (boxes[c][1]+boxes[c][3])/(2*cell)
    lowered=all(center(c)>center('外')+0.15 for c in '。，、')
    gutter=2 if cell==64 else 1
    gutters=all(
        a.crop((x,y,x+cell,y+cell)).getbbox() is None or
        (lambda b:b[0]>=gutter and b[1]>=gutter and b[2]<=cell-gutter and b[3]<=cell-gutter)(
            a.crop((x,y,x+cell,y+cell)).getbbox())
        for a in atlases for x in range(0,32*cell,cell) for y in range(0,32*cell,cell))
    if preview:
        canvas=Image.new('L',(len(phrase)*64,64),32)
        for i,c in enumerate(phrase): canvas.paste(240,(i*64,0,(i+1)*64,64),tile(c).resize((64,64),Image.Resampling.BILINEAR))
        canvas.save(preview)
    return dict(cell=cell,lowered=lowered,gutters=gutters,boxes=boxes,
                passed=cell in (32,64) and lowered and gutters)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('exe','locale','manifest','out','preview'):
        parser.add_argument('--'+name,required=name!='preview',type=Path)
    a=parser.parse_args()
    result=check_font(a.locale,a.manifest,'外面那个开关应该能开门。',a.preview)
    result['native_uv_cases']=check_uv(a.exe,result['cell'])
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('FONT POLISH '+('PASS' if result['passed'] else 'FAIL')+
          f": cell={result['cell']}; lowered={result['lowered']}; gutters={result['gutters']}; UV=3/3")
    raise SystemExit(not result['passed'])
