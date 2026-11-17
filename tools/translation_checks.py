"""Locale-configured editorial checks; never edit translations automatically."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
from assess_resources import require
from locale_catalog import load_catalog
from text_transport import check_contract

ROOT=Path(__file__).resolve().parents[1]


def needs_full_stop_removal(text: str, kind: str, rule: dict) -> bool:
    if kind in rule['except_kinds']:
        return False
    core=text.rstrip().rstrip(rule['closing_marks']).rstrip()
    if not core or core[-1] not in rule['full_stops']:
        return False
    if any(mark in core for mark in rule['commas']):
        return False
    # An ellipsis is not a terminal full stop. Decimal/version dots do not
    # introduce another sentence; ambiguous other punctuation is kept for review.
    if core.endswith('...'):
        return False
    body=re.sub(r'(?<=\d)\.(?=\d)','',core[:-1])
    return not any(mark in body for mark in rule['sentence_endings'])


def check_data(data: dict, policy: dict, glossary: dict) -> list[str]:
    require(policy['schema']==glossary['schema']==1,'unsupported editorial schema')
    require(data['locale']==policy['locale']==glossary['locale'],'editorial locale mismatch')
    terms={}
    for term in glossary['entries']:
        require(term['id'] not in terms,'duplicate glossary ID')
        require(term['source'] and term['preferred'] and term['category'] and term['evidence'],'incomplete glossary entry')
        require(term['status'] in ('active','proposed'),'invalid glossary status')
        terms[term['id']]=term
    require(set(policy['punctuation']['except_kinds']) <= set(policy['text_kinds']),'invalid exception kind')
    errors=[]
    for group in ('bs','pda'):
        for row in data[group]:
            where=f"{group}:{row['id']}"
            kind=row.get('text_kind')
            if 'source' in row or 'source_tokens' in row:
                try:
                    check_contract(row)
                except ValueError as error:
                    errors.append(f'{where}: {error}')
            if kind not in policy['text_kinds']:
                errors.append(f'{where}: missing/invalid text_kind');continue
            if needs_full_stop_removal(row['target'],kind,policy['punctuation']):
                errors.append(f'{where}: single non-narrative sentence without comma must omit terminal full stop')
            for key in row.get('terms',[]):
                term=terms.get(key)
                if term is None or term['status']!='active':
                    errors.append(f'{where}: unknown/unapproved glossary reference {key}');continue
                if 'source' in row and term['source'].casefold() not in row['source'].casefold():
                    errors.append(f'{where}: glossary source mismatch {key}')
                if term['preferred'] not in row['target']:
                    errors.append(f'{where}: expected glossary spelling {key}={term["preferred"]}')
    return errors


def check_locale(directory: Path, data: dict | None = None) -> list[str]:
    read=lambda name:json.loads((directory/name).read_text(encoding='utf-8'))
    return check_data(data if data is not None else load_catalog(directory),read('style.json'),read('glossary.json'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--locale-dir',type=Path,required=True)
    parser.add_argument('--data',type=Path)
    args=parser.parse_args()
    data=json.loads(args.data.read_text(encoding='utf-8')) if args.data else None
    errors=check_locale(args.locale_dir,data)
    for error in errors:print(error)
    print(f'EDITORIAL {"FAIL" if errors else "PASS"}: errors={len(errors)}; punctuation + glossary; no game execution')
    raise SystemExit(2 if errors else 0)
