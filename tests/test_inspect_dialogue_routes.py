import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from inspect_dialogue_routes import SITES, bind_sample, verify_sites


class DialogueRouteTests(unittest.TestCase):
    def test_source_bound_not_runtime_verified(self):
        rows = [dict(id=1, source_sha256=hashlib.sha256(b'fixture').hexdigest(),
                     target='fixture target')]
        report = bind_sample([b'', b'fixture'], rows, ids=(1,))
        self.assertTrue(report[0]['source_bound'])
        self.assertFalse(report[0]['runtime_verified'])
        self.assertNotIn('source', report[0])
        self.assertIsNone(report[0]['review_status'])

    def test_changed_source_rejected(self):
        with self.assertRaisesRegex(ValueError, 'source hash mismatch'):
            bind_sample([b'', b'new'], [dict(id=1, source='old', target='target')], (1,))

    def test_missing_translation_rejected(self):
        with self.assertRaisesRegex(ValueError, 'missing translation'):
            bind_sample([b'', b'fixture'], [], (1,))

    def test_duplicate_id_rejected(self):
        row = dict(id=1, source='fixture', target='target')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            bind_sample([b'', b'fixture'], [row, row], (1,))

    def test_original_sites_match(self):
        by_va = {va: bytes.fromhex(value) for va, value, _ in SITES}
        self.assertEqual(len(verify_sites(lambda va, count: by_va[va][:count])), 8)

    def test_original_site_drift_rejected(self):
        with self.assertRaisesRegex(ValueError, 'original bytes mismatch'):
            verify_sites(lambda va, count: b'\0' * count)


if __name__ == '__main__':
    unittest.main()
