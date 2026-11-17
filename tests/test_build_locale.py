from pathlib import Path
import struct
import json
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from build_locale import encode,decode,dxt3,blob,pack_runtime


class EncodingTests(unittest.TestCase):
    def test_slp3_source_alias_section_precedes_resources(self):
        primary=struct.pack('<I',7)+blob(b'Primary')+blob(b'Target')
        pda=struct.pack('<I',9)+blob(b'PDA')+blob(b'Target')
        exe=struct.pack('<I',2)+blob(b'Exit')+blob(b'Target')
        raw=pack_runtime([primary],[pda],[exe],[('file.dds',b'payload')],{7:[b'Alternate']})
        self.assertEqual(raw[:24],b'SLP3'+struct.pack('<IIIII',1,1,1,1,1))
        alias_at=24+len(primary)+len(pda)+len(exe)
        self.assertEqual(raw[24:alias_at],primary+pda+exe)
        self.assertEqual(raw[alias_at:],struct.pack('<I',7)+blob(b'Alternate')+blob(b'file.dds')+blob(b'payload'))

    def test_slp3_without_aliases_keeps_empty_section(self):
        self.assertEqual(pack_runtime([],[],[],[],{}),b'SLP3'+struct.pack('<IIIII',0,0,0,0,0))

    def test_all_visible_characters_are_tokens(self):
        glyphs={"中":0,",":1,"5":2,"A":3}
        raw=encode("中,5 A\n中",glyphs)
        self.assertEqual(raw,b"\x1f0000\x1f0001\x1f0002 \x1f0003\n\x1f0000")
        self.assertEqual(decode(raw,glyphs),"中,5 A\n中")

    def test_pages_and_capacity(self):
        self.assertEqual(encode("中",{"中":6143}),b"\x1f6143")
        with self.assertRaises(ValueError): encode("中",{"中":6144})

    def test_expanded_atlas_addressing_and_pixel_uv_contract(self):
        profile=json.loads((Path(__file__).resolve().parents[1]/'assets/full-text-contracts.json').read_text(encoding='utf-8'))
        atlas=profile['atlas']
        self.assertEqual(atlas['usable'],6142)
        seen=set()
        for glyph in range(6144):
            page=glyph>>10; local=glyph&1023; col=local&31; row=local>>5
            self.assertTrue(0<=page<6 and 0<=row<32 and 0<=col<32)
            seen.add((page,col,row))
            # Native UV is pixel*16 with an 8-unit half-texel bias.
            left=(col*256+8)/(512*16)
            right=(col*256+248+8)/(512*16)
            self.assertGreater(right,left)
            self.assertLessEqual(right,1)
        self.assertEqual(len(seen),6144)

    def test_unknown_control_rejected(self):
        for value in ("\x00","\x0b","\x1e","\x1f","\x7f"):
            with self.assertRaises(ValueError): encode(value,{value:0})

    def test_greedy_digit_and_partial_token_rejected(self):
        for raw in (b"\x1f00015",b"\x1f",b"\x1f001",b"\x1f000x",b",0000"):
            with self.assertRaises(ValueError): decode(raw,{"中":0})

    def test_dds_header_and_alpha(self):
        from PIL import Image
        import io
        alpha=Image.new("L",(512,512),255)
        dds=dxt3(alpha)
        self.assertEqual(len(dds),262272)
        self.assertEqual(dds[84:88],b"DXT3")
        self.assertEqual(struct.unpack_from("<II",dds,12),(512,512))
        restored=Image.open(io.BytesIO(dds)).convert("RGBA")
        self.assertEqual(restored.getpixel((7,11)),(255,255,255,255))
        alpha.putpixel((7,11),0)
        restored=Image.open(io.BytesIO(dxt3(alpha))).convert("RGBA")
        self.assertEqual(restored.getpixel((7,11)),(255,255,255,0))

    def test_hd_atlas_dds_preserves_bottom_right_cell(self):
        from PIL import Image
        import io
        for side in (1024,2048):
            with self.subTest(side=side):
                alpha=Image.new("L",(side,side),0)
                alpha.putpixel((side-3,side-3),255)
                alpha.putpixel((side-3,side-4),128)
                dds=dxt3(alpha)
                self.assertEqual(len(dds),128+side*side)
                restored=Image.open(io.BytesIO(dds)).convert("RGBA")
                self.assertEqual(restored.getpixel((side-3,side-3))[3],255)
                self.assertEqual(restored.getpixel((side-3,side-4))[3],136)
                self.assertEqual(restored.getpixel((side-1,side-1))[3],0)


if __name__=="__main__": unittest.main()
