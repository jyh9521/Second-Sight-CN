"""Locale-configured editorial checks; never edit translations automatically."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from assess_resources import require
from locale_catalog import load_catalog
from text_transport import check_contract
from audit_locale_policy import audit_text

ROOT=Path(__file__).resolve().parents[1]


def needs_full_stop_removal(text: str, kind: str, rule: dict) -> bool:
    """Compatibility helper; the full check also reports ambiguous findings."""
    role = 'story_or_dialogue' if kind in rule['except_kinds'] else 'other'
    return any(f['kind']=='violation' for f in audit_text(rule['locale'],text,role))


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
    for group in ('bs','pda','exe'):
        for row in data.get(group,[]):
            where=f"{group}:{row['id']}"
            kind=row.get('text_kind')
            if 'source' in row or 'source_tokens' in row:
                try:
                    check_contract(row)
                except ValueError as error:
                    errors.append(f'{where}: {error}')
            if kind not in policy['text_kinds']:
                errors.append(f'{where}: missing/invalid text_kind');continue
            for finding in audit_text(policy['locale'],row['target'],policy['role_mapping'][kind]):
                errors.append(f"{where}: sentence-policy {finding['kind']} at {finding['index']+1}: {finding['reason']}")
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
    policy=read('style.json')
    errors=check_data(data if data is not None else load_catalog(directory),policy,read('glossary.json'))
    from ui_textures import load
    for row in load(directory):
        visible='\n'.join(line['text'] for line in row['layout']['lines'])
        for finding in audit_text(policy['locale'],visible,policy['role_mapping']['ui']):
            errors.append(f"{row['contract']['name']}: sentence-policy {finding['kind']} at {finding['index']+1}: {finding['reason']}")
    return errors


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
