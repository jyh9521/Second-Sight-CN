"""Strict sentence-policy audit, separate from legacy record-level checks.

Read-only game adapter: verified native tokens become neutral visible placeholders;
layout newlines remain within the same logical text. Findings never edit catalogs.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

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


def audit_text(locale: str, text: str, role: str) -> list[dict]:
    if role == 'story_or_dialogue':
        return []
    require(role == 'other', 'unknown role requires classification')
    visible, offsets = visible_text(text)
    return [dict(kind=kind, index=offsets[index], reason=reason)
            for kind, index, reason in analyze_locale_text(locale, visible)]


def audit(directory: Path) -> dict:
    data = load_catalog(directory)
    policy = json.loads((directory / 'style.json').read_text(encoding='utf-8'))
    require(data['locale'] == policy['locale'], 'policy locale mismatch')
    roles = policy['role_mapping']
    findings = []
    checked = exempt = 0

    def inspect(group, row, target):
        nonlocal checked, exempt
        role = roles.get(row['text_kind'])
        if role == 'story_or_dialogue':
            exempt += 1
        else:
            checked += 1
        for finding in audit_text(data['locale'], target, role):
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
