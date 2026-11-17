import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from locale_catalog import load_catalog, bind_sources


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base = dict(bs=[], pda=[], catalogs={'bs': ['menu.json']})
        self.rows = [dict(id=1, source_sha256=hashlib.sha256(b'Label').hexdigest(), source_tokens=[], target='标签')]

    def write(self):
        for name, data in [('poc.json', self.base), ('menu.json', self.rows)]:
            (self.root / name).write_text(json.dumps(data), encoding='utf8')

    def test_bind_hash_and_preserve_input(self):
        self.write()
        data = load_catalog(self.root)
        bound = bind_sources(data, [b'', b'Label'], {})
        self.assertEqual(bound['bs'][0]['source'], 'Label')
        self.assertNotIn('source', data['bs'][0])
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            bind_sources(data, [b'', b'Changed'], {})

    def test_bad_id_rejected(self):
        self.write()
        with self.assertRaisesRegex(ValueError, 'invalid BS'):
            bind_sources(load_catalog(self.root), [b''], {})

    def test_duplicate_rejected(self):
        self.base['bs'] = self.rows[:]
        self.write()
        with self.assertRaisesRegex(ValueError, 'duplicate bs'):
            load_catalog(self.root)

    def test_path_escape_rejected(self):
        self.base['catalogs']['bs'] = ['../outside.json']
        self.write()
        with self.assertRaisesRegex(ValueError, 'filename'):
            load_catalog(self.root)

    def test_ambiguous_source_rejected(self):
        self.rows[0]['source'] = 'Label'
        self.write()
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            load_catalog(self.root)

    def test_missing_token_contract_rejected(self):
        del self.rows[0]['source_tokens']
        self.write()
        with self.assertRaisesRegex(ValueError, 'token contract'):
            load_catalog(self.root)
