"""Load modular translation catalogs; bind source hashes only to supplied assets."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import re
from assess_resources import require


def catalog_files(directory: Path) -> list[str]:
    data = json.loads((directory / 'poc.json').read_text(encoding='utf-8'))
    names = ['poc.json', 'style.json', 'glossary.json', 'font.json']
    if (directory / 'punctuation-context.json').exists():
        names.append('punctuation-context.json')
    if 'ui_textures' in data:
        require(data['ui_textures']=='ui-textures.json', 'invalid UI texture catalog filename')
        names.append(data['ui_textures'])
    if data.get('coverage',{}).get('bs')=='complete_table_inventory': names.append('coverage.json')
    for group, files in data.get('catalogs', {}).items():
        require(group in ('bs', 'pda', 'exe') and isinstance(files, list), 'invalid catalog group')
        for name in files:
            require(isinstance(name, str) and re.fullmatch(r'[a-z0-9-]+\.json', name), 'invalid catalog filename')
            require(name not in names, 'duplicate catalog file')
            names.append(name)
    return names


def load_catalog(directory: Path) -> dict:
    catalog_files(directory)  # Validate before opening any referenced path.
    data = json.loads((directory / 'poc.json').read_text(encoding='utf-8'))
    for group in ('bs', 'pda', 'exe'):
        rows = list(data.get(group, []))
        for name in data.get('catalogs', {}).get(group, []):
            extra = json.loads((directory / name).read_text(encoding='utf-8'))
            require(isinstance(extra, list), 'catalog must contain a list')
            rows.extend(extra)
        require(len({row['id'] for row in rows}) == len(rows), f'duplicate {group} catalog ID')
        for row in rows:
            require(isinstance(row.get('target'), str) and row['target'], 'missing catalog target')
            require(('source' in row) != ('source_sha256' in row), 'exactly one source identity required')
            if 'source_sha256' in row:
                require(re.fullmatch('[0-9a-f]{64}', row['source_sha256']) is not None, 'invalid source hash')
                require(isinstance(row.get('source_tokens'), list), 'missing source token contract')
        data[group] = rows
    return data


def bind_sources(data: dict, bs: list[bytes], pda: dict[str, bytes]) -> dict:
    """No game text is downloaded or guessed; reject stale IDs/hashes atomically."""
    result = copy.deepcopy(data)
    for group in ('bs', 'pda'):
        for row in result[group]:
            key = row['id']
            if group == 'bs':
                require(type(key) is int and 0 < key < len(bs), 'invalid BS catalog ID')
                raw = bs[key]
            else:
                require(key in pda and pda[key], 'invalid PDA catalog ID')
                raw = pda[key]
            if 'source_sha256' in row:
                require(hashlib.sha256(raw).hexdigest() == row['source_sha256'], f'{group}:{key}: source hash mismatch')
            else:
                require(row['source'].encode('cp1252') == raw, f'{group}:{key}: source mismatch')
            row['source'] = raw.decode('cp1252')
    return result
