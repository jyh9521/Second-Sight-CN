"""Bind audited immediate text pointers to a pinned on-disk EXE, read only."""
import copy
import hashlib
import json
from pathlib import Path
import struct
from assess_resources import require

ROOT=Path(__file__).resolve().parents[1]


def contracts() -> dict:
    return json.loads((ROOT/'assets/exe-text-contracts.json').read_text(encoding='utf-8'))


def bind(data: dict, raw: bytes) -> dict:
    import pefile
    result=copy.deepcopy(data)
    profile=contracts()
    require(hashlib.sha256(raw).hexdigest()==profile['executable_sha256'],'unsupported hardcoded text EXE')
    pe=pefile.PE(data=raw)
    try:
        read=lambda va,size:raw[pe.get_offset_from_rva(va-pe.OPTIONAL_HEADER.ImageBase):][:size]
        indexed={r['id']:r for r in profile['records']}
        for row in result.get('exe',[]):
            require(row['id'] in indexed,'unknown executable text ID')
            c=indexed[row['id']];expected=c['source'].encode('ascii')
            require(row['source_sha256']==c['source_sha256']==hashlib.sha256(expected).hexdigest(),'hardcoded text identity mismatch')
            require(read(int(c['source_va'],16),len(expected)+1)==expected+b'\0','hardcoded source mismatch')
            require(read(int(c['patch_va'],16),5)==bytes.fromhex(c['expected'])==b'\x68'+struct.pack('<I',int(c['source_va'],16)),'hardcoded push contract mismatch')
            row['source']=c['source']
    finally:
        pe.close()
    return result
