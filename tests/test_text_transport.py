from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from text_transport import parts, tokens, check_contract, expanded_budget
from build_locale import encode, decode
from locale_catalog import load_catalog


class TransportTests(unittest.TestCase):
    def test_button_placeholder_and_newline_roundtrip(self):
        text = '\vJ \vI按%1\n键'
        mapping = {'按': 0, '键': 1}
        encoded = encode(text, mapping)
        self.assertEqual(encoded, b'\vJ \vI\x1f0000%1\n\x1f0001')
        self.assertEqual(decode(encoded, mapping), text)
        self.assertEqual(tokens(text), ['0b4a', '0b49', '2531', '0a'])

    def test_control_order_and_placeholder_required(self):
        row = dict(id=1, source='\vJ \vI original %1', target='\vJ \vI译文%1')
        check_contract(row)
        for target in ['\vI \vJ译文%1', '\vJ \vI译文', '\vJ \vI译文%2']:
            with self.assertRaisesRegex(ValueError, 'contract'):
                check_contract(dict(row, target=target))

    def test_unknown_and_truncated_opcodes_rejected(self):
        for text in ['\vZ', '\v', '\v\n', '\x1f0001', '\x00']:
            with self.assertRaises(ValueError): list(parts(text))

    def test_literal_percent_is_a_glyph(self):
        mapping = {'%': 1, '率': 2}
        self.assertEqual(decode(encode('率%', mapping), mapping), '率%')
        self.assertEqual(tokens('率%'), [])

    def test_budget_counts_native_expansion_not_opcode_bytes(self):
        self.assertEqual(expanded_budget(b'\vA\vB'), 238)
        self.assertEqual(expanded_budget(b'%1\x1f0000'), 132)
        self.assertEqual(expanded_budget(b'\v1\v2\v3\v4\vG\vH\vI'), 7*59)
        self.assertEqual(expanded_budget(b'\v5\v6\v7\v8\v9\vC\vF\vJ\vK'), 0)
        self.assertEqual(expanded_budget(b'\vD\vE'), 54)

    def test_frozen_metadata_checked_when_binding(self):
        with self.assertRaisesRegex(ValueError, 'metadata'):
            check_contract(dict(id=1, source='\vI', target='\vI', source_tokens=['0b4a']))

    def test_catalog_coverage_and_keyname_budgets(self):
        root = Path(__file__).resolve().parents[1]
        data = load_catalog(root/'locales/zh-CN')
        self.assertEqual(len(data['pda']), 447)
        self.assertEqual(len({r['id'][:4] for r in data['pda']}), 68)
        self.assertTrue({803,6318,6520,6345,5206}.issubset({r['id'] for r in data['bs']}))
        visible = {c for group in ('bs','pda') for row in data[group] for protected,c in parts(row['target']) if not protected and c!=' '}
        self.assertLessEqual(len(visible),1534)
        mapping = dict(zip(sorted(visible),[i for i in range(1536) if i not in (178,184)]))
        for group in ('bs','pda'):
            for row in data[group]:
                with self.subTest(group=group,id=row['id']):
                    check_contract(row)
                    raw=encode(row['target'],mapping)
                    self.assertEqual(decode(raw,mapping),row['target'])
                    if group=='bs':
                        self.assertLessEqual(len(raw),255)
                        self.assertLessEqual(expanded_budget(raw),255)
                    else: self.assertLessEqual(expanded_budget(raw),1800)
                    if row.get('key_name'): self.assertLessEqual(len(raw),27)
