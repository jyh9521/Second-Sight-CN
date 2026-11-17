import copy
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from audit_coverage import audit


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.sources = {'0': '', '1': 'Read abc.txt', '2': 'TEST_ONLY'}
        sha = lambda i: hashlib.sha256(self.sources[str(i)].encode()).hexdigest()
        self.data = {'locale': 'test', 'bs': [{'id': 1, 'source_sha256': sha(1), 'target': '打开abc.txt', 'protected_literals': ['abc.txt']}], 'pda': []}
        self.inventory = {'schema': 1, 'locale': 'test', 'bs_count': 3, 'source_encoding': 'ascii', 'retention_reasons': {'empty': 'Empty source', 'internal': 'Internal identifier'}, 'excluded_bs': [{'id': 0, 'source_sha256': sha(0), 'reason': 'empty'}, {'id': 2, 'source_sha256': sha(2), 'reason': 'internal'}]}

    def test_complete_partition(self):
        self.assertTrue(audit(self.data, self.inventory, self.sources)['source_bound'])

    def test_missing_id(self):
        self.inventory['excluded_bs'].pop()
        with self.assertRaisesRegex(ValueError, 'missing'): audit(self.data, self.inventory)

    def test_overlap(self):
        self.inventory['excluded_bs'][1]['id'] = 1
        with self.assertRaisesRegex(ValueError, 'also excluded'): audit(self.data, self.inventory)

    def test_unknown_reason(self):
        self.inventory['excluded_bs'][1]['reason'] = 'not-translated-yet'
        with self.assertRaisesRegex(ValueError, 'unknown retention'): audit(self.data, self.inventory)

    def test_hash_and_literal_drift(self):
        data = copy.deepcopy(self.data)
        data['bs'][0]['source_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'source mismatch'): audit(data, self.inventory, self.sources)
        self.data['bs'][0]['target'] = '打开文档'
        with self.assertRaisesRegex(ValueError, 'changed protected'): audit(self.data, self.inventory, self.sources)

    def test_identity_not_injected_and_display_literal(self):
        self.inventory['literal_contracts'] = [
            dict(group='bs', ids=[2], mode='not_injected', literals=['TEST_ONLY']),
            dict(group='bs', ids=[1], mode='contains', literals=['abc.txt'])]
        self.assertEqual(audit(self.data, self.inventory, self.sources)['literal_contracts'], 2)
        self.data['bs'][0]['target'] = '打开ABC.TXT'
        with self.assertRaisesRegex(ValueError, 'changed literal'): audit(self.data, self.inventory)

    def test_joint_line_reordering_preserves_literal(self):
        self.data['bs'].append(dict(id=2, source_sha256=self.inventory['excluded_bs'][1]['source_sha256'], target='abc.txt'))
        self.data['bs'][0]['target'] = '打开文件'
        self.data['bs'][0].pop('protected_literals')
        self.inventory['excluded_bs'].pop()
        self.inventory['literal_contracts'] = [dict(group='bs', ids=[1, 2], mode='joint_contains', literals=['abc.txt'])]
        self.assertTrue(audit(self.data, self.inventory, self.sources)['all_ids_accounted'])

    def test_machine_identity_injection_rejected(self):
        self.inventory['literal_contracts'] = [dict(group='bs', ids=[1], mode='not_injected', literals=['abc.txt'])]
        with self.assertRaisesRegex(ValueError, 'must not be injected'): audit(self.data, self.inventory)


if __name__ == '__main__':
    unittest.main()
