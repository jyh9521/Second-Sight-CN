#!/usr/bin/env python3
"""Check the baseline's local Markdown links; external URLs are counted, not fetched."""
import argparse
from pathlib import Path
import re
import unicodedata
from urllib.parse import unquote, urlsplit

EXCLUDED = {'.git', 'original', 'original_game', 'game_original', 'game-files', 'game_files',
            'extracted', 'unpacked', 'decompiled', 'build', 'dist', 'out', 'work', '_work',
            'scratch', 'tmp', 'temp', 'node_modules', '.venv', 'venv',
            # Project-local third-party inputs, not project documentation.
            'FusionFix', 'ReMade With Second Sight Remastered Textures', 'NexusMods'}
DEST = r'(<[^>\n]+>|[^\s)]+)(?:\s+[\"\'][^\n]*?[\"\'])?'
INLINE = re.compile(r'!?\[[^\]\n]*\]\(\s*' + DEST + r'\s*\)')
DEFINITION = re.compile(r'^\s{0,3}\[([^\]]+)\]:\s*' + DEST + r'\s*$', re.M)
REFERENCE = re.compile(r'!?\[([^\]\n]+)\]\[([^\]\n]*)\]')


def prose(text):
    result, fence = [], None
    for line in text.splitlines():
        match = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if match:
            token = match.group(1)
            if fence is None:
                fence = token
                result.append('')
                continue
            if token[0] == fence[0] and len(token) >= len(fence) and not line[match.end():].strip():
                fence = None
                result.append('')
                continue
        result.append('' if fence else line)
    return re.sub(r'`+[^`\n]*`+', '', '\n'.join(result))


def slug(title):
    title = re.sub(r'!?\[([^\]]+)\]\([^)]*\)', r'\1', title)
    title = re.sub(r'<[^>]*>', '', title).replace('`', '').strip().lower()
    return ''.join(char for char in title if char in '-_' or not unicodedata.category(char).startswith(('P', 'S'))).replace(' ', '-')


def anchors(text):
    names, counts = set(), {}
    # Fence exclusion preserves inline-code text in headings for slug generation.
    clean = []
    fenced = False
    for line in text.splitlines():
        if re.match(r'^\s{0,3}(?:`{3,}|~{3,})', line):
            fenced = not fenced
            continue
        if not fenced:
            clean.append(line)
    for line in clean:
        match = re.match(r'^\s{0,3}#{1,6}\s+(.+?)(?:\s+#+)?\s*$', line)
        if match:
            name = slug(match.group(1))
            count = counts.get(name, 0)
            counts[name] = count + 1
            names.add(name if count == 0 else f'{name}-{count}')
    return names


def iter_markdown(root):
    return sorted(path for path in root.rglob('*.md')
                  if path.relative_to(root).parts[0] not in EXCLUDED)


def exact_path(root, destination):
    try:
        relative = destination.relative_to(root)
    except ValueError:
        return False
    current = root
    for part in relative.parts:
        if not current.is_dir() or part not in {entry.name for entry in current.iterdir()}:
            return False
        current /= part
    return current.is_file()


def check_document(root, path):
    text = prose(path.read_text(encoding='utf-8'))
    normalize = lambda name: ' '.join(name.split()).casefold()
    definitions = {normalize(match.group(1)): match.group(2).strip('<>') for match in DEFINITION.finditer(text)}
    targets = [match.group(1).strip('<>') for match in INLINE.finditer(text)]
    errors, external = [], set()
    for match in REFERENCE.finditer(text):
        key = normalize(match.group(2) or match.group(1))
        if key in definitions:
            targets.append(definitions[key])
        else:
            errors.append(f'{path.relative_to(root)}: undefined reference [{key}]')
    remaining = INLINE.sub('', REFERENCE.sub('', DEFINITION.sub('', text)))
    for name in re.findall(r'!?\[([^\]\n]+)\]', remaining):
        if normalize(name) in definitions:
            targets.append(definitions[normalize(name)])
    external.update(re.findall(r'https?://[^\s<>]+', text))
    for target in targets:
        parts = urlsplit(target)
        if parts.scheme or parts.netloc:
            external.add(target)
            continue
        relative = unquote(parts.path)
        if relative.startswith('/') or '\\' in relative:
            errors.append(f'{path.relative_to(root)}: nonportable local path {target}')
            continue
        destination = (path.parent / relative).absolute() if relative else path
        # Normalize '..' but retain spelling for an exact-case comparison on Windows.
        import os
        destination = Path(os.path.abspath(destination))
        if not exact_path(root, destination) or not destination.resolve().is_relative_to(root):
            errors.append(f'{path.relative_to(root)}: missing/case-mismatched local target {target}')
        elif parts.fragment:
            if destination.suffix.lower() != '.md':
                errors.append(f'{path.relative_to(root)}: non-Markdown fragment needs manual verification {target}')
            elif unquote(parts.fragment) not in anchors(destination.read_text(encoding='utf-8')):
                errors.append(f'{path.relative_to(root)}: missing fragment {target}')
    return errors, external


def check_tree(root):
    root = root.resolve()
    errors, external = [], set()
    paths = iter_markdown(root)
    for path in paths:
        found, urls = check_document(root, path)
        errors.extend(found)
        external.update(urls)
    return paths, errors, external


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    paths, errors, external = check_tree(args.root)
    for error in errors:
        print('ERROR: ' + error)
    print(f'DOCS: {len(paths)} files; {len(errors)} local-link errors; {len(external)} external destinations not checked')
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
