"""Personal Chinese policy on plain display text, with explicit review findings."""
import re

COMMAS = frozenset('，,、')
PAIRS = dict(zip('“‘「『（【《〈([', '”’」』）】》〉)]'))
CLOSERS = frozenset(PAIRS.values()) | frozenset('\"\'')
SUSPECT_SYNTAX = re.compile(r'<[/A-Za-z][^>]*>|\{[^{}]*\}|\[[A-Za-z][^\]]*=.*?\]|\\[nr]|\$[A-Za-z]|%(?:\d+\$)?[sdif]')


def analyze(text):
    """Return (kind, index, reason) findings without modifying input.

    Layout newlines/ellipses alone do not terminate a logical sentence.
    Nested punctuation updates its own sentence span, not the enclosing span.
    Ambiguous input is reported for review rather than silently accepted.
    """
    syntax = SUSPECT_SYNTAX.search(text)
    if syntax:
        return [('review', syntax.start(), 'supply verified visible-text spans for apparent markup/control syntax')]
    findings = []
    stack = [{'close': None, 'start': 0, 'open': 0}]
    index = 0
    while index < len(text):
        char = text[index]
        previous = text[index - 1] if index else ''
        following = text[index + 1] if index + 1 < len(text) else ''
        apostrophe = char in ("'", '’') and previous.isascii() and previous.isalpha() and following.isascii() and following.isalpha()
        if apostrophe:
            pass
        elif char in ('\"', "'"):
            if stack[-1]['close'] == char:
                stack.pop()
            else:
                stack.append({'close': char, 'start': index + 1, 'open': index})
        elif char in PAIRS:
            stack.append({'close': PAIRS[char], 'start': index + 1, 'open': index})
        elif char in CLOSERS:
            if stack[-1]['close'] == char:
                stack.pop()
            else:
                findings.append(('review', index, 'unmatched closing quote/bracket'))
        elif char in '！？!?':
            stack[-1]['start'] = index + 1
        elif char == '…' or (char == '.' and following == '.'):
            while index + 1 < len(text) and text[index + 1] == char:
                index += 1
        elif char in '。.':
            is_stop = char == '。'
            if char == '.':
                terminal_context = not following or following.isspace() or following in CLOSERS
                cjk_adjacent = previous and following and '\u3400' <= previous <= '\u9fff' and '\u3400' <= following <= '\u9fff'
                next_cjk = following and '\u3400' <= following <= '\u9fff'
                ambiguous = previous.isdigit() or (previous.isascii() and previous.isalpha())
                if (terminal_context or next_cjk) and ambiguous:
                    findings.append(('review', index, 'numeric/ASCII-word terminal dot needs contextual classification'))
                    stack[-1]['start'] = index + 1
                elif terminal_context or cjk_adjacent:
                    is_stop = True
            if is_stop:
                if not any(c in COMMAS for c in text[stack[-1]['start']:index]):
                    findings.append(('violation', index, 'omit the final full stop in a non-story/non-dialogue sentence without a comma'))
                stack[-1]['start'] = index + 1
        index += 1
    for frame in stack[1:]:
        findings.append(('review', frame['open'], 'unclosed quote/bracket'))
    return findings


def full_stop_positions(text):
    for kind, index, _ in analyze(text):
        if kind == 'violation':
            yield index


def check_sentence_endings(entry):
    if entry['text_role'] != 'other' or not isinstance(entry['target'], str):
        return []
    return [
        f"{entry['id']}: {'zh_sentence_ending' if kind == 'violation' else 'zh_style_review'} "
        f'at character {index + 1}: {reason}'
        for kind, index, reason in analyze(entry['target'])
    ]
