"""Hash-bound offline native cutscene layout replay; never launches the game.

ASI+MAP mode executes its compiled wrapHook, STL string operations, native
measurement, and real wrapBuffers initializer. Only malloc/free/atexit are
synthetic resource boundaries; no text/wrapping algorithm is replaced.
--baseline-with-library and --rollback keep that hook and isolate font scaling.
GPU submission and game subtitle-enable/cookie checks remain bounded fixtures.
"""
from pathlib import Path
import argparse, hashlib, json, struct, re
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *
EXPECTED='4092a8d1fb042dffe9fb95e2185f32cb80390299145e8d453a5e909a06d35fda'
BASE=0x400000; STACK=0x200ff000
WRAP_ENTRY=0x611c70; TRAMPOLINE=0x20008000; INITIALIZER_STOP=0x20000080
HEAP_BASE=0x21000000; HEAP_SIZE=0x01000000
PATCH_BYTES={0x543031:bytes.fromhex('e85ad50c00'),0x5431e8:bytes.fromhex('d905b4749600'),WRAP_ENTRY:bytes.fromhex('81ec04020000')}

def map_exact(text,name):
    rows=[line.split() for line in text.splitlines()]
    found={int(row[2],16) for row in rows if len(row)>=3 and row[1]==name and re.fullmatch(r'[0-9A-Fa-f]{8,16}',row[2])}
    if len(found)!=1:raise ValueError(f'MAP symbol must resolve uniquely: {name}')
    return found.pop()

def validate_options(library,map_path,rollback,draw_only,baseline_with_library=False):
    if baseline_with_library and not (library and map_path):raise ValueError('--baseline-with-library requires --library and --map')
    if baseline_with_library and rollback:raise ValueError('--baseline-with-library and --rollback are mutually exclusive')
    if map_path and not library:raise ValueError('--map requires --library')
    if rollback and not library:raise ValueError('--rollback requires --library')
    if draw_only and library:raise ValueError('--draw-only is a native negative control and excludes --library')


def replay(exe,width,height,glyphs,library=None,draw_only=False,cue_count=1,map_path=None,rollback=False,baseline_with_library=False,input_payload=None):
    validate_options(library,map_path,rollback,draw_only,baseline_with_library)
    data=exe.read_bytes()
    if hashlib.sha256(data).hexdigest()!=EXPECTED: raise ValueError('unsupported executable identity')
    pe=pefile.PE(data=data); u=Uc(UC_ARCH_X86,UC_MODE_32)
    u.mem_map(BASE,(pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095);u.mem_write(BASE,pe.get_memory_mapped_image());u.mem_map(0x20000000,0x100000)
    def w(a,*xs):u.mem_write(a,struct.pack('<'+'I'*len(xs),*xs))
    def f(a,x):u.mem_write(a,struct.pack('<f',x))
    def rd(a):return struct.unpack('<I',u.mem_read(a,4))[0]
    for a in [0x610A96,0x6119F3,0x611A59,0x611D1B,0x611D58,0x612561]:
        if bytes(u.mem_read(a,2))!=b'\x3c\x2c':raise ValueError(f'marker signature mismatch: {a:#x}')
        u.mem_write(a+1,b'\x1f')
    # Synthetic boundaries: render target, current scene, one active cue, BS table.
    w(0x9e88a0,1);w(0x872500,width,height);w(0x95bfa4,0x20001000);w(0x95bfa8,cue_count);w(0x90a338,0x20002000);w(0x20002004,0x20003000)
    input_bytes=input_payload if input_payload is not None else b'\x1f0001'*glyphs+b'\0'
    if not input_bytes.endswith(b'\0') or len(input_bytes)>4096:raise ValueError('fixture payload must be NUL-terminated and within 4096 bytes')
    u.mem_write(0x20003000,input_bytes);w(0x20001000,0,0x40000000,0,0x7f7f7f7f,1)
    w(0x20001014,0,0x40000000,0,0x7f7f7f7f,1)
    margin=int(20*height/480)
    w(0xa05b60,margin);w(0xa05b68,margin);w(0xa05b6c,margin)
    w(0xa0a628,0x20004000);w(0x20004000,0,width);w(0x20004018,height)
    f(0x20005008,1);u.reg_write(UC_X86_REG_EBP,0x20005000);u.reg_write(UC_X86_REG_ESP,STACK-40)
    # Prove unrelated selection is restored rather than leaking caption scaling.
    w(0x9e88a4,24);w(0x9e88a8,0x8ba860);w(0x9e88ac,0x8babc0)
    original_style=bytes(u.mem_read(0x8bab6c,28));exports={};joint={};initializing=False
    boundary_counts={'malloc':0,'free':0,'atexit':0};heap_next=HEAP_BASE
    for address,expected in PATCH_BYTES.items():
        if bytes(u.mem_read(address,len(expected)))!=expected:raise ValueError(f'native patch signature mismatch: {address:#x}')
    if library:
        dll=pefile.PE(str(library));b=dll.OPTIONAL_HEADER.ImageBase
        if dll.FILE_HEADER.Machine!=0x14c:raise ValueError('library must be x86')
        u.mem_map(b,(dll.OPTIONAL_HEADER.SizeOfImage+4095)&~4095);u.mem_write(b,dll.get_memory_mapped_image())
        exports={s.name.decode():b+s.address for s in getattr(getattr(dll,'DIRECTORY_ENTRY_EXPORT',None),'symbols',[]) if s.name}
        if map_path:
            from replay_glyph_batches import map_symbol
            symbols=map_path.read_text(encoding='utf-8',errors='replace')
            stamp=re.search(r'Timestamp is ([0-9A-Fa-f]+)',symbols)
            if not stamp or int(stamp.group(1),16)!=dll.FILE_HEADER.TimeDateStamp:raise ValueError('MAP timestamp does not match supplied ASI')
            exports={'Begin':map_symbol(symbols,'beginCutscene@subtitle_layout'), 'End':map_symbol(symbols,'endCutsceneHook@subtitle_layout')}
            joint={key:map_exact(symbols,name) for key,name in {
                'wrapHook':'?wrapHook@@YAPADPBDM@Z',
                'originalWrap':'?originalWrap@@3P6APADPBDM@ZA',
                'initializer':'??__EwrapBuffers@@YAXXZ',
                'malloc':'__malloc_base','free':'__free_base','atexit':'_atexit'}.items()}
        if not all(name in exports for name in ('Begin','End')):raise ValueError('production ASI requires --map; probe DLL requires Begin/End exports')
        for name,address in {**exports,**joint}.items():
            if not b<=address<b+dll.OPTIONAL_HEADER.SizeOfImage:raise ValueError(f'MAP/export {name} outside supplied ASI image')
        if joint:
            # Original 6-byte prologue contains no relative operand.
            prologue=PATCH_BYTES[WRAP_ENTRY]
            u.mem_write(TRAMPOLINE,prologue+b'\xe9'+struct.pack('<i',WRAP_ENTRY+len(prologue)-(TRAMPOLINE+len(prologue)+5)))
            w(joint['originalWrap'],TRAMPOLINE)
            u.mem_write(WRAP_ENTRY,b'\xe9'+struct.pack('<i',joint['wrapHook']-WRAP_ENTRY-5)+b'\x90')
            u.mem_map(0,0x1000);w(0,0xffffffff) # synthetic x86 SEH/TEB boundary
            u.mem_map(HEAP_BASE,HEAP_SIZE)
        if not baseline_with_library:
            u.mem_write(0x543031,b'\xe8'+struct.pack('<i',exports['Begin']-0x543036))
            u.mem_write(0x5431e8,b'\xe9'+struct.pack('<i',exports['End']-0x5431ed)+b'\x90')
    if rollback:
        # Isolate the scale variable: the production wrapHook remains installed.
        for address in (0x543031,0x5431e8):u.mem_write(address,PATCH_BYTES[address])
    scaled=bool(library and not baseline_with_library and not rollback)
    exit_regs=[]
    protected=(UC_X86_REG_EAX,UC_X86_REG_EBX,UC_X86_REG_ECX,UC_X86_REG_EDX,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP,UC_X86_REG_ESP,UC_X86_REG_EFLAGS)
    out={'resolution':[width,height],'glyphs':glyphs,'cue_count':cue_count,'synthetic_margin':margin,
         'input_identity':{'kind':'synthetic literal payload' if input_payload is not None else 'synthetic repeated encoded glyph','marker':31,'slot':1,'payload_bytes':len(input_bytes),'sha256':hashlib.sha256(input_bytes).hexdigest()},
         'joint_wrap_enabled':bool(joint),'wrap_before_measure':True,'executed_hooks':{'begin':0,'end':0,'wrapHook':0,'wrap_initializer':0,'native_measure':0,'original_wrap':0}};draws=[]
    def hook(u,a,n,arg):
        nonlocal heap_next
        if initializing and a==INITIALIZER_STOP:u.emu_stop();return
        for key,target in [('begin',exports.get('Begin')),('end',exports.get('End')),('wrapHook',joint.get('wrapHook')),('wrap_initializer',joint.get('initializer')),('native_measure',0x611940),('original_wrap',TRAMPOLINE)]:
            if a==target:out['executed_hooks'][key]+=1
        if joint and a in (joint['malloc'],joint['free'],joint['atexit']):
            esp=u.reg_read(UC_X86_REG_ESP);value=0
            if a==joint['malloc']:
                size=rd(esp+4);value=heap_next;heap_next=(heap_next+max(size,1)+15)&~15
                if heap_next>HEAP_BASE+HEAP_SIZE:raise ValueError('synthetic allocation budget exceeded')
                boundary_counts['malloc']+=1
            elif a==joint['free']:boundary_counts['free']+=1
            else:boundary_counts['atexit']+=1
            u.reg_write(UC_X86_REG_EAX,value);u.reg_write(UC_X86_REG_EIP,rd(esp));u.reg_write(UC_X86_REG_ESP,esp+4);return

        if scaled and a==0x5431e8:exit_regs.extend(u.reg_read(r) for r in protected)
        if a==(0x5431ee if scaled else 0x5431e8):
            out['exit_registers_preserved']=not scaled or exit_regs==[u.reg_read(r) for r in protected]
            u.emu_stop();return
        if a==0x5430fd and joint and out['executed_hooks']['wrapHook']<len(draws)+1:out['wrap_before_measure']=False
        if a==0x543107:out['measured_width']=u.reg_read(UC_X86_REG_EAX)
        if a==0x54311b:out['line_count']=u.reg_read(UC_X86_REG_EAX)
        if a in (0x50bd60,0x7b397a,0x613330):
            esp=u.reg_read(UC_X86_REG_ESP)
            if a==0x50bd60:u.reg_write(UC_X86_REG_EAX,1)
            if a==0x613330:
                args=struct.unpack('<ffIII',u.mem_read(esp+4,20));style=rd(0x9e88ac)
                sx,sy=struct.unpack('<ff',u.mem_read(style+8,8))
                if draw_only:sx*=height/480;sy*=height/480
                wrapped=bytes(u.mem_read(args[2],2048)).split(b'\0',1)[0]
                out['payload_preserved']=wrapped.replace(b'\n',b'')==input_bytes[:-1]
                out['wrapped_sha256']=hashlib.sha256(wrapped).hexdigest()
                out['wrapped_bytes']=len(wrapped)
                out['max_line_glyphs']=max(line.count(b'\x1f') for line in wrapped.split(b'\n'))
                draws.append({'x':args[0],'y':args[1],'sx':sx,'sy':sy,'glyph_height':16*.87*sy})
            u.reg_write(UC_X86_REG_EIP,rd(esp));u.reg_write(UC_X86_REG_ESP,esp+4)
    u.hook_add(UC_HOOK_CODE,hook)
    if joint:
        initializing=True;w(STACK-4,INITIALIZER_STOP);u.reg_write(UC_X86_REG_ESP,STACK-4)
        u.emu_start(joint['initializer'],0,count=200000)
        if u.reg_read(UC_X86_REG_EIP)!=INITIALIZER_STOP:raise AssertionError('wrap initializer did not return')
        initializing=False;u.reg_write(UC_X86_REG_ESP,STACK-40);u.reg_write(UC_X86_REG_EBP,0x20005000)
    u.emu_start(0x54302f,0,count=2000000)
    out['allocation_boundaries']=boundary_counts
    if joint and out['executed_hooks']['wrapHook']!=cue_count:raise AssertionError('compiled wrapHook execution count differs from active cue count')
    if u.reg_read(UC_X86_REG_EIP)!=(0x5431ee if scaled else 0x5431e8):raise AssertionError('native scope did not reach its exit')
    out.update(draws=draws,style21_unchanged=original_style==bytes(u.mem_read(0x8bab6c,28)),style_restored=(rd(0x9e88ac)==0x8babc0 and rd(0x9e88a4)==24 and rd(0x9e88a8)==0x8ba860))
    if len(draws)!=cue_count:raise AssertionError('unexpected active cue draw count')
    if not cue_count:
        out.update(proportional_scale_ok=True,safe_area_ok=True,measurement_agrees=True,centered=True,payload_preserved=True)
        return out
    d=draws[0];expected=height/480
    out['proportional_scale_ok']=abs(d['sy']-expected)<1e-5
    out['measurement_agrees']=abs(out['measured_width']-out['max_line_glyphs']*13.92*d['sx'])<1.01
    out['centered']=abs(d['x']+out['measured_width']/2-width/2)<=1
    out['safe_area_ok']=d['x']>=margin and d['x']+out['measured_width']<=width-margin and d['y']>=margin and d['y']+out['line_count']*16*d['sy']<=height-margin
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--exe',type=Path,required=True);ap.add_argument('--library',type=Path);ap.add_argument('--map',type=Path);ap.add_argument('--rollback',action='store_true');ap.add_argument('--baseline-with-library',action='store_true');ap.add_argument('--draw-only',action='store_true');ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    try:validate_options(args.library,args.map,args.rollback,args.draw_only,args.baseline_with_library)
    except ValueError as error:ap.error(str(error))
    rows=[replay(args.exe,w,h,n,args.library,args.draw_only,map_path=args.map,rollback=args.rollback,baseline_with_library=args.baseline_with_library) for w,h in [(640,480),(1280,720),(1920,1080),(2880,1800),(3840,2160)] for n in [7,72]]
    if args.library and not args.rollback and not args.baseline_with_library: rows += [replay(args.exe,2880,1800,7,args.library,cue_count=n,map_path=args.map) for n in (0,2)]
    good=all(x['payload_preserved'] and x['wrap_before_measure'] and x['proportional_scale_ok'] and x['safe_area_ok'] and x['measurement_agrees'] and x['centered'] and x['exit_registers_preserved'] and x['style21_unchanged'] and (x['style_restored'] if args.library and not args.rollback and not args.baseline_with_library else True) for x in rows)
    result={'library_sha256':hashlib.sha256(args.library.read_bytes()).hexdigest() if args.library else None,'map_sha256':hashlib.sha256(args.map.read_bytes()).hexdigest() if args.map else None,'baseline_with_library':args.baseline_with_library,'rollback':args.rollback,'kind':'offline native x86 layout replay','game_launched':False,'pixel_render_verified':False,'passed':good,'cases':rows}
    args.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(('PASS' if good else 'FAIL')+f': native subtitle layout {sum(x["proportional_scale_ok"] for x in rows)}/{len(rows)} proportional; original style unchanged={all(x["style21_unchanged"] for x in rows)}')
    return 0 if good else 1
if __name__=='__main__':raise SystemExit(main())
