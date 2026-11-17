from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from text_transport import parts, tokens, check_contract, expanded_budget, bs_limit, bs_expanded_limit, DEFERRED_BS_IDS, COMPOSED_BS_IDS, UNRESOLVED_BS_IDS
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
        self.assertLessEqual(len(visible),6142)
        mapping = dict(zip(sorted(visible),[i for i in range(6144) if i not in (178,184)]))
        for group in ('bs','pda'):
            for row in data[group]:
                with self.subTest(group=group,id=row['id']):
                    check_contract(row)
                    raw=encode(row['target'],mapping)
                    self.assertEqual(decode(raw,mapping),row['target'])
                    if group=='bs':
                        self.assertLessEqual(len(raw),bs_limit(row["id"]))
                        self.assertLessEqual(expanded_budget(raw,identifier=row["id"]),bs_expanded_limit(row["id"]))
                    else: self.assertLessEqual(expanded_budget(raw),1800)
                    if row.get('key_name'): self.assertLessEqual(len(raw),27)

    def test_printf_is_source_bound_not_visible_text(self):
        row=dict(id=4511,source='Mode: %s',target='模式：%s')
        check_contract(row)
        mapping={'模':0,'式':1,'：':2}
        raw=encode(row['target'],mapping)
        self.assertTrue(raw.endswith(b'%s'))
        self.assertEqual(decode(raw,mapping),row['target'])
        self.assertEqual(expanded_budget(raw),142)
        self.assertEqual(tokens(row['source']),['2573'])
        for bad in [dict(row,id=850),dict(row,target='模式')]:
            with self.assertRaises(ValueError):check_contract(bad)

    def test_long_ids_are_consumer_allowlisted(self):
        for identifier in (4498,4501,5497,5184,5500,5503,5506,3027,5684,5901):
            self.assertEqual(bs_limit(identifier),4095)
        for identifier in (850,5499,5502,4511):self.assertEqual(bs_limit(identifier),255)

    def test_terminal_and_deferred_budgets_are_separate(self):
        for identifier in (5922,5924,5926): self.assertEqual(bs_limit(identifier),1023)
        self.assertEqual(DEFERRED_BS_IDS,{313,314,2912,3029,4637,4638,5494}|set(range(3846,3853))|set(range(3644,3649)))
        self.assertEqual(COMPOSED_BS_IDS,set(range(3644,3649)))
        for identifier in DEFERRED_BS_IDS:self.assertEqual(bs_limit(identifier),4095)

    def test_projection_tutorial_uses_inspected_argument_bounds(self):
        self.assertEqual(expanded_budget(b'%1%2\v2',identifier=4478),128)
        self.assertEqual(expanded_budget(b'%1%2\v2'),313)

    def test_proved_template_slots_do_not_use_generic_127(self):
        self.assertEqual(expanded_budget(b'%1%2%3%4%5',identifier=2909),165)
        self.assertEqual(expanded_budget(b'%1%2%3%4%5',identifier=3336),197)
        self.assertEqual(bs_expanded_limit(3336),510)
        self.assertEqual(bs_limit(3336),255)
        self.assertEqual(bs_expanded_limit(2909),255)
