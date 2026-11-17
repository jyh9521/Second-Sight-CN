"""Strict sentence-policy audit, separate from legacy record-level checks.

Read-only game adapter: verified native tokens become neutral visible placeholders;
layout newlines remain within the same logical text. Findings never edit catalogs.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re

from assess_resources import require
from locale_catalog import load_catalog
from locale_policies import analyze_locale_text
from text_transport import check_contract, parts
from ui_textures import load as load_ui


def visible_text(text: str) -> tuple[str, list[int]]:
    display, positions = [], []
    offset = 0
    for protected, value in parts(text):
        if protected and value not in ('\n', '\t'):
            display.append('\ufffc')  # button label/template slot, not punctuation
            positions.append(offset)
        else:
            display.extend(value)
            positions.extend(range(offset, offset + len(value)))
        offset += len(value)
    return ''.join(display), positions


def _punctuation_shape(text: str, index: int, purpose: str) -> bool:
    """Conservative syntax checks, not permission to approve arbitrary spans."""
    char = text[index]
    before, after = text[:index], text[index + 1:]
    if purpose == 'year_abbreviation':
        return char == "'" and (not before or before[-1].isspace()) and bool(re.match(r'[0-9]{2}(?![0-9])', after))
    if purpose == 'name_initial':
        return char == '.' and bool(re.search(r'(?<![A-Za-z])[A-Z]$', before)) and (not after or after[0].isspace() or after[0] in ')）')
    if purpose == 'numbered_list':
        return char in ')）' and bool(re.fullmatch(r'[0-9]+', before)) and bool(after.strip())
    if purpose == 'fragment_open':
        return char in '(（' and not any(c in after for c in ')）') and bool(after.strip())
    return False


def punctuation_contexts(directory: Path, data: dict) -> dict:
    """Bind reviewed non-sentence punctuation to exact source/target revisions.

    Each annotation owns one character only. It never exempts a record, role,
    full stop or unreviewed punctuation. Catalog changes invalidate the review.
    """
    path = directory / 'punctuation-context.json'
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding='utf-8'))
    require(set(payload) == {'schema', 'locale', 'entries'}, 'invalid punctuation context fields')
    require(payload['schema'] == 1 and payload['locale'] == data['locale'], 'punctuation context schema/locale mismatch')
    require(isinstance(payload['entries'], list), 'punctuation contexts must be a list')
    rows = {(group, row['id']): row for group in ('bs', 'pda', 'exe') for row in data.get(group, [])}
    contexts = {}
    fields = {'group', 'id', 'source_sha256', 'target_sha256', 'source_span', 'target_span', 'purpose', 'evidence'}
    for entry in payload['entries']:
        require(set(entry) == fields, 'invalid punctuation context entry fields')
        key = (entry['group'], entry['id'])
        require(key in rows, 'punctuation context record is missing')
        row = rows[key]
        source_hash = row.get('source_sha256')
        if 'source' in row:
            bound_hash = hashlib.sha256(row['source'].encode('cp1252')).hexdigest()
            require(source_hash is None or bound_hash == source_hash, 'punctuation context source identity mismatch')
            source_hash = bound_hash
        require(entry['source_sha256'] == source_hash, 'stale punctuation context source')
        require(entry['target_sha256'] == hashlib.sha256(row['target'].encode('utf-8')).hexdigest(), 'stale punctuation context target')
        require(isinstance(entry['evidence'], str) and entry['evidence'].strip(), 'punctuation context needs evidence')
        for side in ('source', 'target'):
            span = entry[side + '_span']
            require(isinstance(span, dict) and set(span) == {'start', 'end', 'text'}, 'invalid punctuation span')
            require(type(span['start']) is int and span['start'] >= 0 and type(span['end']) is int
                    and span['end'] == span['start'] + 1 and isinstance(span['text'], str)
                    and len(span['text']) == 1, 'punctuation context must bind one character')
            allowed = {'year_abbreviation': "'", 'name_initial': '.', 'numbered_list': ')）', 'fragment_open': '(（'}
            require(entry['purpose'] in allowed and span['text'] in allowed[entry['purpose']],
                    'invalid punctuation context purpose/character')
            # Source is present in a source-bound export/build, otherwise its raw
            # CP1252 fingerprint is the contract, not a guessed English string.
            if side in row:
                text = row[side]
                require(text[span['start']:span['end']] == span['text'], 'punctuation context span mismatch')
                require(_punctuation_shape(text, span['start'], entry['purpose']), 'invalid punctuation context purpose/shape')
        target = entry['target_span']
        positions = contexts.setdefault(key, {})
        require(target['start'] not in positions, 'duplicate punctuation context position')
        positions[target['start']] = target['text']
    return contexts


def audit_text(locale: str, text: str, role: str, non_sentence: dict | None = None) -> list[dict]:
    if role == 'story_or_dialogue':
        return []
    require(role == 'other', 'unknown role requires classification')
    visible, offsets = visible_text(text)
    if non_sentence:
        require(all(index in offsets and text[index] == char for index, char in non_sentence.items()),
                'punctuation context must refer to unchanged visible characters')
        # Only the policy projection changes; the catalog/display remains exact.
        visible = ''.join('\ufffc' if offset in non_sentence else char for char, offset in zip(visible, offsets))
    return [dict(kind=kind, index=offsets[index], reason=reason)
            for kind, index, reason in analyze_locale_text(locale, visible)]


def audit(directory: Path) -> dict:
    data = load_catalog(directory)
    policy = json.loads((directory / 'style.json').read_text(encoding='utf-8'))
    require(data['locale'] == policy['locale'], 'policy locale mismatch')
    roles = policy['role_mapping']
    contexts = punctuation_contexts(directory, data)
    findings = []
    checked = exempt = 0

    def inspect(group, row, target):
        nonlocal checked, exempt
        role = roles.get(row['text_kind'])
        if role == 'story_or_dialogue':
            exempt += 1
        else:
            checked += 1
        for finding in audit_text(data['locale'], target, role, contexts.get((group, row['id']))):
            findings.append(dict(group=group, id=row['id'], text_kind=row['text_kind'],
                                 target_sha256=hashlib.sha256(target.encode('utf-8')).hexdigest(),
                                 **finding))

    for group in ('bs', 'pda', 'exe'):
        for row in data[group]:
            check_contract(row)
            inspect(group, row, row['target'])
    for row in load_ui(directory):
        # Lines are layout, not sentence boundaries. Do not exempt later lines
        # from a comma or truncate a sentence at each display row.
        inspect('image', {'id': row['contract']['name'], 'text_kind': 'ui'},
                '\n'.join(line['text'] for line in row['layout']['lines']))
    return dict(schema=1, locale=data['locale'], authority='locales/'+data['locale']+'/STYLE.md',
                status='fail' if findings else 'pass', checked_records=checked,
                narrative_exempt_records=exempt, narrative_classification_reviewed=False,
                findings=findings, mutations=0, game_launched=False)


def summary(report: dict) -> str:
    findings = report['findings']
    records = len({(f['group'], f['id']) for f in findings})
    violations = sum(f['kind'] == 'violation' for f in findings)
    reviews = sum(f['kind'] == 'review' for f in findings)
    return (f"SENTENCE_POLICY {report['status'].upper()}: records={records}; "
            f"violations={violations}; review={reviews}; mutations=0; game_launched=false")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--locale-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    report = audit(args.locale_dir)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(summary(report))
    return 2 if report['findings'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
