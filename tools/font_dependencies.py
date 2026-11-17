"""Pinned font dependencies selected by locale data, not embedded in tooling."""
import hashlib
import json
from pathlib import Path
import re
import urllib.request
from assess_resources import require


def read_config(path: Path) -> dict:
    config=json.loads(path.read_text(encoding='utf-8'))
    require(config['schema']==1,'unsupported font config')
    require(re.fullmatch(r'[0-9a-f]{40}',config['commit']) is not None,'font commit must be pinned')
    for key in ('font','license'):
        item=config[key]
        require(Path(item['name']).name==item['name'] and not any(c in item['name'] for c in '\\/:') and item['name'] not in ('.','..'),'invalid dependency filename')
        require(re.fullmatch(r'[0-9a-f]{64}',item['sha256']) is not None,'invalid dependency hash')
        require(item['url'].startswith('https://') and '/'+config['commit']+'/' in item['url'],'dependency URL must pin declared commit')
    return config


def dependency(cache: Path, item: dict) -> Path:
    path=cache/item['name']
    if not path.exists():
        data=urllib.request.urlopen(item['url'],timeout=120).read()
        require(hashlib.sha256(data).hexdigest()==item['sha256'],'font download hash mismatch')
        cache.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
    require(hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256'],'font dependency hash mismatch')
    return path


def notice(config: dict) -> str:
    return '\n'.join([
        f"Generated localization atlas source: {config['family']} {config['style']}, Version {config['version']}.",
        config['copyright'], 'Licensed under SIL Open Font License 1.1; include OFL.txt with generated atlases.',
        'Source: '+config['font']['url'], 'Pinned commit: '+config['commit'],
        'SHA-256: '+config['font']['sha256'],
        'The generated atlas is a format-converted subset, not the original font binary.', ''])
