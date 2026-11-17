"""Source-bound native control/template contracts for locale text."""
from __future__ import annotations
import re
from assess_resources import require

# Current PC catalogs use VT + button opcode, numbered %1 placeholders, and LF.
# Other controls are rejected instead of guessing their interpreter contract.
CONTROL = re.compile(r'\x0b[1-9A-K]|%[1-9](?![0-9])|%s|\n|\t')


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
    if '%s' in row['target']:
        require(row['id']==4511, 'printf contract is only established for BS 4511')
    expected = tokens(row['source']) if 'source' in row else row['source_tokens']
    require(tokens(row['target']) == expected, f"{row['id']}: control/template contract mismatch")
    if 'source_tokens' in row:
        require(expected == row['source_tokens'], f"{row['id']}: source token metadata mismatch")


TEMPLATE_BOUNDS = {2441: [59, 59, 10], 2442: [59, 59, 10], 2443: [59, 59, 10], 2444: [59, 59, 27, 10], 2445: [59, 59, 27, 10], 2446: [59, 59, 27, 10], 2447: [59, 59, 27, 10], 2448: [59, 59, 27, 10], 2449: [10, 59], 2896: [10, 59, 27], 2897: [59, 27], 2907: [10, 59, 27], 2908: [59, 27], 2909: [10, 59, 27, 10, 59], 2910: [10, 59, 27], 2911: [27, 10, 59], 3336: [10, 59, 10, 59, 59], 3337: [10, 59], 3820: [10, 59], 3821: [10, 59], 4261: [10, 59, 10, 59], 4478: [10, 59]}

def expanded_budget(encoded: bytes, *, template_bytes: int = 127, identifier: int | None = None) -> int:
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
        elif encoded[cursor:cursor+1] == b'%' and encoded[cursor+1:cursor+2] in tuple(bytes([n]) for n in range(49,58)) + (b's',):
            slot=encoded[cursor+1]-ord("1")
            bounds=TEMPLATE_BOUNDS.get(identifier,())
            total += bounds[slot] if 0<=slot<len(bounds) else template_bytes
            cursor += 2
        else:
            total += 1
            cursor += 1
    return total


# Exact IDs selected by the two inspected notice/mail body tables. Other BS
# retain the conservative UI limit until their consumer contract is recorded.
LONG_BS_IDS = frozenset((
    4498, 4501, 5408, 5497, 5184, 5500, 5503, 5506,
    3027, 3608, 3609, 3650, 3923, 3924, 3928, 3929, 3930, 3931,
    3933, 3958, 4004, 4415, 4561, 4639, 5330, 5331, 5682, 5683,
    5684, 5685, 5898, 5899, 5900, 5901,
))
TERMINAL_BS_IDS = frozenset((5922,5924,5926))
# Never rebound into the BS table: exact source match at approved long-wrap callers only.
COMPOSED_BS_IDS = frozenset(range(3644,3649))
UNRESOLVED_BS_IDS = frozenset((313,314,2912,3029,3846,3847,3848,3849,3850,3851,3852,4637,4638,5494))
DEFERRED_BS_IDS = UNRESOLVED_BS_IDS | COMPOSED_BS_IDS

def bs_limit(identifier: int) -> int:
    return 4095 if identifier in LONG_BS_IDS | DEFERRED_BS_IDS else 1023 if identifier in TERMINAL_BS_IDS else 255


def bs_expanded_limit(identifier: int) -> int:
    # 3336 uses a 512-byte formatter, then HUD rejects inputs >=511.
    return 510 if identifier==3336 else bs_limit(identifier)
