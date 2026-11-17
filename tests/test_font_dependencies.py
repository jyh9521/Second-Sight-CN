import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from font_dependencies import read_config,dependency,notice


class FontDependencyTests(unittest.TestCase):
    def test_repository_config_is_pinned_and_attributed(self):
        config=read_config(ROOT/'locales/zh-CN/font.json')
        self.assertEqual(config['family'],'Source Han Sans SC')
        self.assertIn(config['font']['sha256'],notice(config))
        self.assertIn('SIL Open Font License',notice(config))

    def test_invalid_filename_hash_and_unpinned_url(self):
        config=read_config(ROOT/'locales/zh-CN/font.json')
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)/'config.json'
            for key,value in [('name','../outside'),('sha256','bad'),('url','http://example.test/font')]:
                changed=json.loads(json.dumps(config));changed['font'][key]=value
                path.write_text(json.dumps(changed),encoding='utf-8')
                with self.assertRaises(ValueError):read_config(path)

    def test_cached_hash_mismatch_never_downloads(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);(root/'font.otf').write_bytes(b'changed')
            item={'name':'font.otf','url':'https://example.test/font','sha256':hashlib.sha256(b'expected').hexdigest()}
            with patch('font_dependencies.urllib.request.urlopen') as download:
                with self.assertRaises(ValueError):dependency(root,item)
                download.assert_not_called()


if __name__=='__main__':unittest.main()
