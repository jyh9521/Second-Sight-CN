import copy
import hashlib
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from assess_resources import StringTable
from source_variants import validate_profile, validate_tables, aliases_for, pack_aliases


def bs(*strings):
    offset = len(strings) * 4
    pointers = []
    pool = bytearray()
    for text in strings:
        pointers.append(offset + len(pool))
        pool.extend(text + b'\0')
    return struct.pack('<' + 'I' * len(pointers), *pointers) + pool


class SourceVariantTests(unittest.TestCase):
    def setUp(self):
        self.raw = {'first': bs(b'', b'Favourite %1', b'Same'),
                    'second': bs(b'', b'Favorite %1', b'Same')}
        self.profile = dict(schema=1, primary='first', table_slots=3, sources=[
            dict(id=name, archive='pak/a.pak', member=f'data/{name}.bs', size=len(raw),
                 sha256=hashlib.sha256(raw).hexdigest()) for name, raw in self.raw.items()])
        self.rows = [dict(id=1, source='Favourite %1', target='项目%1'), dict(id=2, source='Same', target='相同')]

    def test_exact_variant_uses_same_target_without_mutation(self):
        original = copy.deepcopy(self.rows)
        tables = validate_tables(self.profile, self.raw)
        aliases = aliases_for(self.rows, self.profile, tables)
        self.assertEqual(aliases, {1: [b'Favorite %1']})
        self.assertEqual(self.rows, original)

    def test_sparse_pack_records_are_source_only(self):
        count, raw = pack_aliases({7: [b'A', b'B'], 2: [b'C']})
        expected = b''.join(struct.pack('<II', index, 1) + value for index, value in [(2, b'C'), (7, b'A'), (7, b'B')])
        self.assertEqual((count, raw), (3, expected))

    def test_changed_resource_hash_rejected(self):
        raw = dict(self.raw, second=bs(b'', b'Changed! %1', b'Same'))
        with self.assertRaisesRegex(ValueError, 'identity'):
            validate_tables(self.profile, raw)

    def test_resource_size_rejected_independently(self):
        profile = copy.deepcopy(self.profile)
        profile['sources'][1]['size'] += 1
        with self.assertRaisesRegex(ValueError, 'identity'):
            validate_tables(profile, self.raw)

    def test_slot_count_mismatch_rejected(self):
        profile = copy.deepcopy(self.profile)
        profile['table_slots'] += 1
        with self.assertRaisesRegex(ValueError, 'slot count'):
            validate_tables(profile, self.raw)

    def test_missing_source_rejected(self):
        with self.assertRaisesRegex(ValueError, 'source set'):
            validate_tables(self.profile, {'first': self.raw['first']})

    def test_unknown_profile_or_duplicate_source_rejected(self):
        profile = copy.deepcopy(self.profile)
        profile['schema'] = 2
        with self.assertRaises(ValueError): validate_profile(profile)
        profile = copy.deepcopy(self.profile)
        profile['sources'].append(profile['sources'][1])
        with self.assertRaisesRegex(ValueError, 'duplicate'): validate_profile(profile)

    def test_archive_traversal_rejected(self):
        for path in ('../a.pak', '/a.pak', 'C:/a.pak', 'pak/../a.pak', 'pak\\a.pak'):
            profile = copy.deepcopy(self.profile)
            profile['sources'][0]['archive'] = path
            with self.assertRaisesRegex(ValueError, 'path'): validate_profile(profile)

    def test_variant_control_change_is_not_accepted(self):
        tables = {name: StringTable(raw) for name, raw in self.raw.items()}
        tables['second'] = StringTable(bs(b'', b'Favorite %2', b'Same'))
        with self.assertRaisesRegex(ValueError, 'control'): aliases_for(self.rows, self.profile, tables)

    def test_primary_source_mismatch_is_not_hidden(self):
        tables = validate_tables(self.profile, self.raw)
        with self.assertRaisesRegex(ValueError, 'primary source'):
            aliases_for([dict(id=1, source='Favorite %1')], self.profile, tables)

    def test_variants_are_deduplicated(self):
        profile = copy.deepcopy(self.profile)
        profile['sources'].append(dict(profile['sources'][1], id='third'))
        raw = dict(self.raw, third=self.raw['second'])
        self.assertEqual(aliases_for(self.rows, profile, validate_tables(profile, raw)), {1: [b'Favorite %1']})

    def test_primary_only_profile_has_no_aliases(self):
        profile = copy.deepcopy(self.profile)
        profile['sources'] = profile['sources'][:1]
        tables = validate_tables(profile, {'first': self.raw['first']})
        self.assertEqual(aliases_for(self.rows, profile, tables), {})
        self.assertEqual(pack_aliases({}), (0, b''))

    def test_duplicate_selected_id_rejected(self):
        tables = validate_tables(self.profile, self.raw)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            aliases_for(self.rows + self.rows[:1], self.profile, tables)

    def test_pack_alias_limits_match_native_parser(self):
        values = [bytes([65 + n]) for n in range(7)]
        self.assertEqual(pack_aliases({1: values})[0], 7)
        for invalid in (values + [b'H'], [b'x' * 4097]):
            with self.assertRaises(ValueError): pack_aliases({1: invalid})
        self.assertEqual(pack_aliases({1: [b'x' * 4096]})[0], 1)

    def test_invalid_alias_source_and_id_rejected(self):
        for aliases in ({0: [b'A']}, {6526: [b'A']}, {1: [b'']}, {1: [b'A\0B']}, {1: [b'A', b'A']}):
            with self.assertRaises(ValueError): pack_aliases(aliases)


if __name__ == '__main__': unittest.main()
