"""Exact, resource-identified BS source variants sharing one localized target.

Profiles describe input resources, not translation data. No spelling normalization
or fuzzy matching is permitted: an alias is the same table slot in a fully
verified source resource and must retain its native control-token contract.
"""
from __future__ import annotations
import hashlib
from pathlib import Path, PurePosixPath
import re
import struct

from assess_resources import Pak, StringTable, require
from text_transport import tokens


MAX_SOURCES = 8
MAX_SLOTS = 6526
MAX_SOURCE_BYTES = 4096


def _relative_path(value: str) -> bool:
    return (isinstance(value, str) and bool(value) and not any(c in value for c in '\\:\0')
            and not value.startswith('/') and all(p not in ('', '.', '..') for p in value.split('/'))
            and str(PurePosixPath(value)) == value)


def validate_profile(profile: dict) -> None:
    require(profile.get('schema') == 1, 'unsupported source variant schema')
    slots = profile.get('table_slots')
    require(type(slots) is int and 2 <= slots <= MAX_SLOTS, 'invalid source variant slot count')
    sources = profile.get('sources')
    require(isinstance(sources, list) and 1 <= len(sources) <= MAX_SOURCES, 'invalid source variant count')
    identifiers = set()
    for source in sources:
        require(isinstance(source, dict), 'invalid source variant record')
        identifier = source.get('id')
        require(isinstance(identifier, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', identifier) is not None,
                'invalid source variant identifier')
        require(identifier not in identifiers, 'duplicate source variant identifier')
        identifiers.add(identifier)
        require(_relative_path(source.get('archive')) and _relative_path(source.get('member')),
                'invalid source variant path')
        require(type(source.get('size')) is int and source['size'] > slots * 4, 'invalid source variant size')
        require(isinstance(source.get('sha256'), str) and re.fullmatch(r'[0-9a-f]{64}', source['sha256']) is not None,
                'invalid source variant hash')
    require(profile.get('primary') in identifiers, 'source variant primary missing')


def validate_tables(profile: dict, raw_by_id: dict[str, bytes]) -> dict[str, StringTable]:
    validate_profile(profile)
    require(set(raw_by_id) == {source['id'] for source in profile['sources']}, 'source set mismatch')
    tables = {}
    for source in profile['sources']:
        identifier = source['id']
        raw = raw_by_id[identifier]
        require(len(raw) == source['size'] and hashlib.sha256(raw).hexdigest() == source['sha256'],
                f'{identifier}: source resource identity mismatch')
        table = StringTable(raw)
        require(len(table.strings) == profile['table_slots'], f'{identifier}: source variant slot count mismatch')
        tables[identifier] = table
    return tables


def load_tables(game: Path, profile: dict) -> dict[str, StringTable]:
    validate_profile(profile)
    archives = {}
    raw = {}
    root = game.resolve()
    for source in profile['sources']:
        archive = (root / source['archive']).resolve()
        require(archive.is_relative_to(root), 'source archive path escapes game root')
        if archive not in archives:
            archives[archive] = Pak(archive.read_bytes())
        raw[source['id']] = archives[archive].member(source['member'])
    return validate_tables(profile, raw)


def aliases_for(rows: list[dict], profile: dict, tables: dict[str, StringTable]) -> dict[int, list[bytes]]:
    validate_profile(profile)
    require(set(tables) == {source['id'] for source in profile['sources']}, 'source set mismatch')
    require(all(len(table.strings) == profile['table_slots'] for table in tables.values()), 'source variant slot count mismatch')
    primary = tables[profile['primary']]
    aliases = {}
    seen = set()
    for row in rows:
        identifier = row['id']
        require(type(identifier) is int and 0 < identifier < profile['table_slots'], 'invalid source variant BS ID')
        require(identifier not in seen, 'duplicate source variant BS ID')
        seen.add(identifier)
        expected = row['source'].encode('cp1252')
        require(primary.strings[identifier] == expected, f'{identifier}: primary source mismatch')
        alternate = []
        for source in profile['sources']:
            candidate = tables[source['id']].strings[identifier]
            if candidate == expected or candidate in alternate:
                continue
            require(0 < len(candidate) <= MAX_SOURCE_BYTES and b'\0' not in candidate, 'invalid alias source')
            require(tokens(candidate.decode('cp1252')) == tokens(row['source']), f'{identifier}: source variant control mismatch')
            alternate.append(candidate)
        if alternate:
            aliases[identifier] = alternate
    return aliases


def pack_aliases(aliases: dict[int, list[bytes]]) -> tuple[int, bytes]:
    """SLP3 sparse records: u32 BS ID, u32 byte length, exact source bytes."""
    require(all(type(identifier) is int and 0 < identifier < MAX_SLOTS for identifier in aliases), 'invalid alias BS ID')
    records = []
    for identifier in sorted(aliases):
        values = aliases[identifier]
        require(1 <= len(values) < MAX_SOURCES, 'invalid alias count')
        require(all(isinstance(value, bytes) and 0 < len(value) <= MAX_SOURCE_BYTES and b'\0' not in value for value in values),
                'invalid alias source')
        require(len(set(values)) == len(values), 'duplicate alias source')
        records.extend(struct.pack('<II', identifier, len(value)) + value for value in values)
    return len(records), b''.join(records)
