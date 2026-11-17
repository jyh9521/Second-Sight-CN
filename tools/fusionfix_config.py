"""Byte-preserving FusionFix window policy; no game or DLL execution."""
from __future__ import annotations
import re


def borderless_config(data: bytes) -> bytes:
    """Change only [MAIN] WindowMode's single numeric byte to 2.

    Reject missing/ambiguous keys instead of rewriting or normalizing the INI.
    Comments, other sections, whitespace, line endings and all other values stay
    byte-identical. The caller separately pins the complete upstream input.
    """
    section=b''
    main_count=0
    positions=[]
    offset=0
    for line in data.splitlines(keepends=True):
        body=line.rstrip(b'\r\n')
        header=re.fullmatch(rb'[ \t]*\[([^\]\r\n]+)\][ \t]*(?:[;#].*)?',body)
        if header:
            section=header[1].strip().lower()
            if section==b'main': main_count+=1
        elif section==b'main' and re.match(rb'[ \t]*WindowMode[ \t]*=',body,re.IGNORECASE):
            value=re.fullmatch(rb'[ \t]*WindowMode[ \t]*=[ \t]*([012])[ \t]*(?:[;#].*)?',body,re.IGNORECASE)
            if not value: raise ValueError('invalid MAIN.WindowMode value')
            positions.append(offset+value.start(1))
        offset+=len(line)
    if main_count!=1 or len(positions)!=1:
        raise ValueError('expected one MAIN section and one MAIN.WindowMode key')
    at=positions[0]
    return data[:at]+b'2'+data[at+1:]
