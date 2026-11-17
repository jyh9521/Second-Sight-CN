"""Source-bound native control/template contracts for locale text."""
from __future__ import annotations
import re
from assess_resources import require

# Current PC catalogs use VT + button opcode, numbered %1 placeholders, and LF.
# Other controls are rejected instead of guessing their interpreter contract.
CONTROL = re.compile(r'\x0b[1-9A-K]|%[1-9](?![0-9])|\n|\t')


def parts(text: str):
    cursor = 0
    while cursor < len(text):
        match = CONTROL.match(text, cursor)
        if match:
            yield True, match.group()
            cursor = match.end()
        else:
            char = text[cursor]
            require(ord(char) >= 32 and ord(char) != 127, 'unapproved native control')
            yield False, char
            cursor += 1


def tokens(text: str) -> list[str]:
    return [value.encode('ascii').hex() for protected, value in parts(text) if protected]


def check_contract(row: dict) -> None:
    expected = tokens(row['source']) if 'source' in row else row['source_tokens']
    require(tokens(row['target']) == expected, f"{row['id']}: control/template contract mismatch")
    if 'source_tokens' in row:
        require(expected == row['source_tokens'], f"{row['id']}: source token metadata mismatch")


def expanded_budget(encoded: bytes, *, template_bytes: int = 127) -> int:
    """Pinned PC opcode bounds; see TEXT_CONTRACTS_005.md.

    Native key names are separately capped at 27 encoded bytes. This is an
    offline consumer budget, not a declaration that every UI layout fits.
    """
    cursor = total = 0
    while cursor < len(encoded):
        if encoded[cursor] == 11:
            require(cursor + 1 < len(encoded), 'truncated button opcode')
            code=chr(encoded[cursor+1])
            require(code in '123456789ABCDEFGHIJK', 'unknown button opcode')
            total += 59 if code in '1234GHI' else 119 if code in 'AB' else 27 if code in 'DE' else 0
            cursor += 2
        elif encoded[cursor:cursor+1] == b'%' and encoded[cursor+1:cursor+2] in tuple(bytes([n]) for n in range(49,58)):
            total += template_bytes
            cursor += 2
        else:
            total += 1
            cursor += 1
    return total
