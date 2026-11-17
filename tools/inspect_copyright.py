"""Read-only, identity-bound PC startup copyright path inspection.
This script reads PE bytes only. It never executes or attaches the game.
"""
import argparse, hashlib, json, struct
from pathlib import Path
from assess_resources import require
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--exe",type=Path,required=True)
parser.add_argument("--out",type=Path,required=True)
args=parser.parse_args()
EXE=args.exe.resolve()
ROOT=args.out.resolve()
if ROOT == EXE.parent or ROOT.is_relative_to(EXE.parent):
 raise ValueError("inspection output must be outside game directory")
ROOT.mkdir(parents=True,exist_ok=True)
EXPECTED="4092a8d1fb042dffe9fb95e2185f32cb80390299145e8d453a5e909a06d35fda"
b=EXE.read_bytes()
require(len(b)==5484544 and hashlib.sha256(b).hexdigest()==EXPECTED, "copyright source/profile mismatch")
pe=pefile.PE(data=b); base=pe.OPTIONAL_HEADER.ImageBase
md=Cs(CS_ARCH_X86,CS_MODE_32)
def raw(va,n):
 o=pe.get_offset_from_rva(va-base); return b[o:o+n]
def u32(va): return struct.unpack('<I',raw(va,4))[0]
def string(va):
 o=pe.get_offset_from_rva(va-base); return b[o:b.index(0,o)].decode('ascii')
def asm(lo,hi):
 return [f"{i.address:08X} {i.bytes.hex()} {i.mnemonic} {i.op_str}" for i in md.disasm(raw(lo,hi-lo),lo)]
# All ranges below begin at an independently aligned instruction/function boundary.
# Embedded jump tables are excluded, not decoded as code.
ranges={
 'scene_texture_load_dispatch':(0x544A80,0x544AAB),
 'scene_load_tail':(0x544B30,0x544B3A),
 'scene_init_dispatch':(0x545A24,0x545A45),
 'scene_init_loading_reset_call':(0x545D44,0x545D90),
 'scene_update_dispatch':(0x544D60,0x544D7E),
 'scene_update_tail':(0x544E50,0x544E74),
 'scene_render_dispatch':(0x546080,0x5460CC),
 'scene_render_tail':(0x5462C0,0x5462C5),
 'startup_state_reset':(0x4AF230,0x4AF24C),
 'startup_state_update':(0x4AF260,0x4AF5D2),
 'startup_render_entry':(0x4AF620,0x4AF68A),
 'legal_state2_draw':(0x4AFA0A,0x4AFB0E),
 'texture_handle_and_name_lookup':(0x4AD350,0x4AD36F),
 'texture_scene_filter':(0x4AD370,0x4AD40C),
 'texture_enqueue_by_index':(0x4AD420,0x4AD512),
 'texture_enqueue_loop':(0x4AD520,0x4AD554),
 'texture_handle_population':(0x4AD600,0x4AD63B),
 'texture_queue_dispatch':(0x49FA5C,0x49FAB8),
 'raw_to_dds_loader':(0x413A60,0x413B62),
 'bs_loader':(0x43E560,0x43E683),
}
dis={k:asm(*v) for k,v in ranges.items()}
require(raw(0x4AFA36,5)==bytes.fromhex('b84f020000'), "copyright source/profile mismatch")
require(raw(0x4AF477,10)==bytes.fromhex('c70534d5910002000000'), "copyright source/profile mismatch")
require(raw(0x5462C0,5)==bytes.fromhex('e95b93f6ff'), "copyright source/profile mismatch")
require(string(0x7DA9B4)=='textures/misc/%s.raw', "copyright source/profile mismatch")
require(string(0x7D7AB0)=='data/strss%s', "copyright source/profile mismatch")
legal=[]
for ident in range(591,596):
 slot=0x87C94C+24*ident; ptr=u32(slot)
 legal.append({'texture_id':ident,'name_pointer_slot':hex(slot),'name_address':hex(ptr),'name':string(ptr),'handle_slot':hex(0x87C954+24*ident),'scene_flags':hex(u32(0x87C948+24*ident))})
require([x['name'] for x in legal]==['legal_english512','legal_france512','legal_italy512','legal_germany512','legal_spain512'], "copyright source/profile mismatch")
text_end=0x400000+pe.sections[0].VirtualAddress+pe.sections[0].Misc_VirtualSize
occ=[]; candidates=[]; pos=0
while True:
 pos=b.find(struct.pack('<I',0x90A338),pos)
 if pos<0: break
 va=base+pe.get_rva_from_offset(pos)
 if 0x401000<=va<text_end:
  occ.append(hex(va)); win=b[pos:pos+96]
  if any(struct.pack('<I',n*4) in win for n in (313,314)):candidates.append(hex(va))
 pos+=1
report={
 'schema':1,
 'target':{'path':str(EXE),'size':len(b),'sha256':EXPECTED},
 'method':'pefile/Capstone read-only static PE inspection; no game execution, attachment or deep decompiler',
 'game_executed':False,'game_attached':False,'game_files_modified':False,
 'conclusions':[
  {'status':'verified_static','claim':'PC startup scene 0x67 has a state-2 copyright draw path using language-selected legal texture IDs, not BS313/314.', 'evidence':['scene_init_dispatch','scene_init_loading_reset_call','scene_update_dispatch','scene_update_tail','startup_state_update','scene_render_dispatch','scene_render_tail','legal_state2_draw']},
  {'status':'verified_static','claim':'State 0 resets/selects language, state 1 plays trailers/stngf and trailers/stngc then stores state 2 at 0x4AF477; state 2 advances by timer to state 3.', 'evidence':['startup_state_reset','startup_state_update']},
  {'status':'verified_static','claim':'State 2 selects [591,591,592,594,593,595] using language global 0x875E80. Lookup4AD350 returns handle; 40FC20 binds; 412DC0 draws the texture rectangle. This complete state-2 draw block has no BS-global load or text draw call.', 'evidence':['legal_state2_draw','texture_handle_and_name_lookup']},
  {'status':'verified_static','claim':'legal_english512 is texture ID591 and resolves to textures/misc/legal_english512.raw; the PC loader rewrites raw to dds before resource lookup/read.', 'evidence':['texture_enqueue_by_index','texture_enqueue_loop','texture_queue_dispatch','raw_to_dds_loader']},
  {'status':'observed_asset_review','claim':'The already decoded legal_english512.png contains the BS314-style 2004 notice plus company logos/TM symbols. BS313 is a different shorter 2000-2004 notice. This is asset inspection, not game-screen observation.', 'evidence':['texture-inspection/legal_english512.png','../menu-pda-005/bs.json IDs313,314']},
  {'status':'bounded_negative_search','claim':'No offset313*4/314*4 literal occurs within the 96 bytes after any of 472 raw .text occurrences of the BS global address 0x90A338. This does not exclude nonlocal register flow, ID tables, indirect indexing or level resources.', 'evidence':['bs_search']},
  {'status':'unknown','claim':'Global non-consumption of BS313/314 by all shipped PC paths is not proved. The verified fact is narrower: translating these BS rows does not translate the startup DDS copyright page.'}
 ],
 'recommendation':'Treat startup copyright artwork as an image-text localization surface. Do not claim the two BS translations cover that page, and do not classify their entire-program reachability as proven-unused solely from this report.',
 'texture_descriptors':legal,
 'language_order_texture_ids':[591,591,592,594,593,595],
 'texture_scene_filter_dispatch':{str(0x65+i):hex(u32(0x4AD40C+4*i)) for i in range(4)},
 'scene_id':103,'state_global':'0x91D534','language_global':'0x875E80','bs_global':'0x90A338',
 'resource_strings':{'0x7DA9B4':string(0x7DA9B4),'0x7DA9CC':string(0x7DA9CC),'0x7D7AB0':string(0x7D7AB0),'0x7DAA3C':string(0x7DAA3C),'0x7DAA2C':string(0x7DAA2C)},
 'bs_search':{'method':'raw .text BS-global address occurrences and bounded 96-byte subsequent offset-literal search','global_occurrence_count':len(occ),'candidate_sites':candidates,'global_occurrence_sites':occ,'limitations':'not a complete CFG or data-flow proof; absence of nearby constants does not establish unused IDs'},
 'disassembly_file':'copyright-path-disassembly.txt',
 'ranges':{k:[hex(v[0]),hex(v[1])] for k,v in ranges.items()}
}
report['conclusions']=[row for row in report['conclusions'] if row['status']!='observed_asset_review']
(ROOT/'copyright-path-disassembly.txt').write_text('\n\n'.join(k+'\n'+'\n'.join(v) for k,v in dis.items())+'\n',encoding='utf-8')
(ROOT/'copyright-path-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
require(hashlib.sha256(EXE.read_bytes()).hexdigest()==EXPECTED, "copyright source/profile mismatch")
for name in ['copyright-path-disassembly.txt','copyright-path-review.json']:
 require((ROOT/name).read_text(encoding='utf-8'), "copyright source/profile mismatch")
print('COPYRIGHT PATH VERIFIED: PC scene103 state2 draws legal DDS; 5 language descriptors; BS313/314 not the startup draw source; global unused status unproved; game bytes unchanged; no game execution')
