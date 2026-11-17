import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from ui_textures import dxt3_solid,load,validate_sources


class UiTexturesTests(unittest.TestCase):
    def test_rectangular_dds_alpha_and_color(self):
        from PIL import Image
        alpha=Image.new('L',(256,64),255);alpha.putpixel((10,9),0)
        data=dxt3_solid(alpha,(14<<11)|(48<<5)|30)
        self.assertEqual(len(data),16512)
        self.assertEqual(struct.unpack_from('<II',data,12),(64,256))
        decoded=Image.open(io.BytesIO(data)).convert('RGBA')
        self.assertEqual(decoded.getpixel((0,0)),(115,195,247,255))
        self.assertEqual(decoded.getpixel((10,9)),(115,195,247,0))

    def test_source_bound_mirrors(self):
        row={'contract':dict(name='synthetic',source_bytes=3,source_sha256=hashlib.sha256(b'abc').hexdigest(),mirror_count=2)}
        validate_sources([row],{'synthetic':[b'abc',b'abc']})
        for copies in ([b'abc'],[b'abc',b'bad']):
            with self.assertRaises(ValueError):validate_sources([row],{'synthetic':copies})

    def test_reject_unsupported_texture_and_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'poc.json').write_text(json.dumps(dict(locale='xx',ui_textures='ui-textures.json')))
            for rows in ([dict(name='../unreviewed',lines=[])],[dict(name='x')]*2):
                (root/'ui-textures.json').write_text(json.dumps(dict(schema=1,locale='xx',resources=rows)))
                with self.assertRaises(ValueError):load(root)

    def test_no_ui_asset_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'poc.json').write_text('{}')
            self.assertEqual(load(root),[])

    def test_checked_in_layout(self):
        rows=load(Path(__file__).resolve().parents[1]/'locales/zh-CN')
        self.assertEqual(len(rows),1)
        self.assertTrue(rows[0]['contract']['vertical_flip'])
        self.assertEqual(rows[0]['contract']['width'],256)
