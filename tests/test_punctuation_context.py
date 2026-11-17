import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from audit_locale_policy import audit_text, punctuation_contexts
from locale_catalog import catalog_files, load_catalog
from translation_checks import check_data


def digest(text, encoding='utf-8'):
    return hashlib.sha256(text.encode(encoding)).hexdigest()


class ContextualPunctuationTests(unittest.TestCase):
    def fixture(self, source='Contact F. Giddler.', target='联系 F. 医生。', purpose='name_initial', source_index=9, target_index=4):
        row = dict(id=1, source=source, target=target, text_kind='ui')
        entry = dict(group='bs', id=1, source_sha256=digest(source, 'cp1252'), target_sha256=digest(target),
                     source_span=dict(start=source_index, end=source_index+1, text=source[source_index]),
                     target_span=dict(start=target_index, end=target_index+1, text=target[target_index]),
                     purpose=purpose, evidence='Synthetic source-bound punctuation context')
        return dict(locale='zh-CN', bs=[row]), dict(schema=1, locale='zh-CN', entries=[entry])

    def load(self, data, payload):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'punctuation-context.json').write_text(json.dumps(payload), encoding='utf-8')
            return punctuation_contexts(path, data)

    def test_initial_does_not_exempt_following_sentence_full_stop(self):
        data, payload = self.fixture()
        contexts = self.load(data, payload)
        text = data['bs'][0]['target']
        self.assertEqual([f['kind'] for f in audit_text('zh-CN', text, 'other')], ['review', 'violation'])
        self.assertEqual(audit_text('zh-CN', text, 'other', contexts['bs', 1]), [
            dict(kind='violation', index=8, reason='omit the final full stop in a non-story/non-dialogue sentence without a comma')])
        self.assertEqual(text, '联系 F. 医生。')

    def test_specific_semantics_keep_exact_visible_text(self):
        samples = [
            ("X '92 GAME", "X '92游戏", 'year_abbreviation', 2, 2),
            ('1) Rotate camera', '1）旋转镜头', 'numbered_list', 1, 1),
            ('appears jammed (code', '卡住了 (代码', 'fragment_open', 15, 4),
        ]
        for sample in samples:
            with self.subTest(purpose=sample[2]):
                data, payload = self.fixture(*sample)
                before = copy.deepcopy(data)
                contexts = self.load(data, payload)
                self.assertEqual(audit_text('zh-CN', sample[1], 'other', contexts['bs', 1]), [])
                self.assertEqual(data, before)

    def test_target_or_source_edit_invalidates_context(self):
        for side in ('target', 'source'):
            data, payload = self.fixture()
            data['bs'][0][side] += ' changed'
            with self.subTest(side=side), self.assertRaisesRegex(ValueError, 'stale punctuation context'):
                self.load(data, payload)

    def test_hashed_source_revision_must_match(self):
        data, payload = self.fixture()
        row = data['bs'][0]
        row['source_sha256'] = digest(row.pop('source'), 'cp1252')
        self.load(data, payload)
        row['source_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'stale punctuation context source'):
            self.load(data, payload)

    def test_source_bound_span_checked_not_just_target(self):
        data, payload = self.fixture()
        payload['entries'][0]['source_span'].update(start=2, end=3)
        with self.assertRaisesRegex(ValueError, 'span mismatch'):
            self.load(data, payload)

    def test_whole_record_duplicate_unknown_and_full_stop_annotations_rejected(self):
        for mutation in ('range', 'duplicate', 'purpose', 'character', 'extra', 'missing_record'):
            data, payload = self.fixture()
            entry = payload['entries'][0]
            if mutation == 'range': entry['target_span']['end'] += 1
            elif mutation == 'duplicate': payload['entries'].append(copy.deepcopy(entry))
            elif mutation == 'purpose': entry['purpose'] = 'skip_record'
            elif mutation == 'character': entry['target_span'].update(start=8, end=9, text='。')
            elif mutation == 'extra': entry['ignore_all'] = True
            elif mutation == 'missing_record': entry['id'] = 2
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.load(data, payload)

    def test_ascii_sentence_dot_cannot_masquerade_as_initial(self):
        data, payload = self.fixture('Done.', '完成.', 'name_initial', 4, 2)
        with self.assertRaisesRegex(ValueError, 'purpose/shape'):
            self.load(data, payload)

    def test_native_tokens_offsets_survive_context_projection(self):
        target = '按\x0b2联系 F. 医生。'
        data, payload = self.fixture(target=target, target_index=7)
        contexts = self.load(data, payload)
        self.assertEqual([f['index'] for f in audit_text('zh-CN', target, 'other', contexts['bs', 1])], [11])

    def test_repository_contexts_cover_only_six_reviewed_characters(self):
        directory = ROOT / 'locales/zh-CN'
        data = load_catalog(directory)
        contexts = punctuation_contexts(directory, data)
        self.assertEqual(set(contexts), {('bs', i) for i in (2411, 3275, 3632, 4067, 4509, 4510)})
        self.assertEqual(sum(map(len, contexts.values())), 6)
        self.assertIn('punctuation-context.json', catalog_files(directory))
        read = lambda name: json.loads((directory/name).read_text(encoding='utf-8'))
        raw = check_data(data, read('style.json'), read('glossary.json'))
        self.assertEqual(len(raw), 6)
        self.assertTrue(all('sentence-policy review' in e for e in raw))
        self.assertEqual(check_data(data, read('style.json'), read('glossary.json'), contexts), [])


if __name__ == '__main__':
    unittest.main()
