from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from build_locale import encode,decode,dxt3


class EncodingTests(unittest.TestCase):
    def test_all_visible_characters_are_tokens(self):
        glyphs={"中":0,",":1,"5":2,"A":3}
        raw=encode("中,5 A\n中",glyphs)
        self.assertEqual(raw,b"\x1f0000\x1f0001\x1f0002 \x1f0003\n\x1f0000")
        self.assertEqual(decode(raw,glyphs),"中,5 A\n中")

    def test_pages_and_capacity(self):
        self.assertEqual(encode("中",{"中":1535}),b"\x1f1535")
        with self.assertRaises(ValueError): encode("中",{"中":1536})

    def test_unknown_control_rejected(self):
        for value in ("\x00","\x0b","\x1e","\x1f","\x7f"):
            with self.assertRaises(ValueError): encode(value,{value:0})

    def test_greedy_digit_and_partial_token_rejected(self):
        for raw in (b"\x1f00015",b"\x1f",b"\x1f001",b"\x1f000x",b",0000"):
            with self.assertRaises(ValueError): decode(raw,{"中":0})

    def test_dds_header_and_alpha(self):
        from PIL import Image
        import io
        alpha=Image.new("L",(256,256),255)
        dds=dxt3(alpha)
        self.assertEqual(len(dds),65664)
        self.assertEqual(dds[84:88],b"DXT3")
        self.assertEqual(struct.unpack_from("<II",dds,12),(256,256))
        restored=Image.open(io.BytesIO(dds)).convert("RGBA")
        self.assertEqual(restored.getpixel((7,11)),(255,255,255,255))
        alpha.putpixel((7,11),0)
        restored=Image.open(io.BytesIO(dxt3(alpha))).convert("RGBA")
        self.assertEqual(restored.getpixel((7,11)),(255,255,255,0))


if __name__=="__main__": unittest.main()
