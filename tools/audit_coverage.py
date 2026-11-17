"""Account for every original string ID without publishing its source text.

Coverage is a resource inventory, not evidence of in-game rendering or QA.
An excluded row needs a source hash and a concrete retention reason. Translated
and excluded IDs must form a disjoint, complete partition of the pinned table.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from assess_resources import require
from locale_catalog import load_catalog


def audit(data: dict, inventory: dict, sources: dict[str, str] | None = None) -> dict:
    require(inventory['schema'] == 1, 'unsupported coverage inventory schema')
    require(inventory['locale'] == data['locale'], 'coverage locale mismatch')
    count = inventory['bs_count']
    require(isinstance(count, int) and count > 0, 'invalid BS table count')
    translated = {row['id']: row for row in data['bs']}
    require(len(translated) == len(data['bs']), 'duplicate translated ID')
    excluded = {}
    for row in inventory['excluded_bs']:
        identifier = row['id']
        require(identifier not in excluded, 'duplicate excluded ID')
        require(identifier not in translated, 'translated ID is also excluded')
        require(row.get('reason') in inventory['retention_reasons'], 'unknown retention reason')
        digest = row.get('source_sha256', '')
        require(len(digest) == 64 and all(c in '0123456789abcdef' for c in digest), 'invalid excluded source hash')
        excluded[identifier] = row
    require(set(translated) | set(excluded) == set(range(count)), 'missing or out-of-range BS inventory ID')
    # A file name may move between linked display lines during translation;
    # compare the explicitly declared group, never normalize machine values.
    contracts = inventory.get('literal_contracts', [])
    for contract in contracts:
        require(contract['group'] == 'bs', 'unsupported literal contract resource')
        identifiers = contract['ids']
        require(bool(identifiers) and all(i in translated or i in excluded for i in identifiers), 'invalid literal contract IDs')
        mode = contract['mode']
        require(mode in ('not_injected', 'contains', 'joint_contains'), 'unknown literal contract mode')
        require(bool(contract['literals']) and all(isinstance(x, str) and x for x in contract['literals']), 'invalid literal contract values')
        if mode == 'not_injected':
            require(all(i in excluded for i in identifiers), 'machine identity must not be injected')
        else:
            require(all(i in translated for i in identifiers), 'literal display group is not translated')
            target = '\n'.join(translated[i]['target'] for i in identifiers)
            for literal in contract['literals']:
                require(literal in target, f'BS {identifiers}: changed literal {literal}')
                if sources is not None:
                    source = '\n'.join(sources[str(i)] for i in identifiers)
                    require(literal in source and target.count(literal) == source.count(literal), f'BS {identifiers}: literal count differs')
    if sources is not None:
        require(set(sources) == {str(i) for i in range(count)}, 'source inventory table mismatch')
        for identifier, row in (translated | excluded).items():
            original = sources[str(identifier)].encode(inventory['source_encoding'])
            digest = hashlib.sha256(original).hexdigest()
            expected = row.get('source_sha256')
            if expected is None:
                expected = hashlib.sha256(row['source'].encode(inventory['source_encoding'])).hexdigest()
            require(digest == expected, f'BS {identifier}: coverage source mismatch')
            for literal in row.get('protected_literals', []):
                require(literal and literal in sources[str(identifier)], f'BS {identifier}: invalid protected literal')
                require(row['target'].count(literal) == sources[str(identifier)].count(literal), f'BS {identifier}: changed protected literal')
    return {
        'bs_total': count,
        'bs_translated': len(translated),
        'bs_retained': len(excluded),
        'pda_translated': len(data['pda']),
        'all_ids_accounted': True,
        'source_bound': sources is not None,
        'game_executed': False,
        'literal_contracts': len(contracts),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--locale-dir', type=Path, required=True)
    parser.add_argument('--source-json', type=Path, help='local extracted BS table; never committed')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    inventory = json.loads((args.locale_dir / 'coverage.json').read_text(encoding='utf-8'))
    source = json.loads(args.source_json.read_text(encoding='utf-8')) if args.source_json else None
    result = audit(load_catalog(args.locale_dir), inventory, source)
    if args.out:
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('COVERAGE PASS: ' + json.dumps(result, sort_keys=True))
