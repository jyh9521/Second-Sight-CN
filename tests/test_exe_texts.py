import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import exe_texts


class SyntheticPe:
    class OPTIONAL_HEADER:
        ImageBase=0x400000
    def get_offset_from_rva(self,rva):return rva
    def close(self):pass


class ExeTextTests(unittest.TestCase):
    def setUp(self):
        self.raw=bytearray(128); self.raw[32:37]=b'Test\0'; self.raw[64:69]=b'\x68'+struct.pack('<I',0x400020)
        self.row=dict(id=1,source_sha256=hashlib.sha256(b'Test').hexdigest(),target='测试',source_tokens=[])
        self.profile=dict(executable_sha256=hashlib.sha256(self.raw).hexdigest(),records=[dict(id=1,source='Test',source_sha256=self.row['source_sha256'],source_va='0x400020',patch_va='0x400040',expected=self.raw[64:69].hex())])

    def bind(self,data,raw=None):
        with patch.object(exe_texts,'contracts',return_value=self.profile),patch('pefile.PE',return_value=SyntheticPe()):
            return exe_texts.bind(data,bytes(self.raw if raw is None else raw))

    def test_source_binding_preserves_input(self):
        data=dict(exe=[self.row]);before=copy.deepcopy(data)
        self.assertEqual(self.bind(data)['exe'][0]['source'],'Test')
        self.assertEqual(data,before)

    def test_bad_exe_identity_rejected(self):
        with self.assertRaisesRegex(ValueError,'EXE'):self.bind(dict(exe=[self.row]),b'wrong')

    def test_unknown_id_and_stale_source_rejected(self):
        for key,value in [('id',99),('source_sha256','0'*64)]:
            row=dict(self.row);row[key]=value
            with self.assertRaises(ValueError):self.bind(dict(exe=[row]))

    def test_modified_instruction_rejected_even_if_profile_hash_updated(self):
        self.raw[64]=0x90;self.profile['executable_sha256']=hashlib.sha256(self.raw).hexdigest()
        with self.assertRaisesRegex(ValueError,'push contract'):self.bind(dict(exe=[self.row]))

    def test_native_contracts_match_profile(self):
        root=Path(__file__).resolve().parents[1]
        text=(root/'src/localization.cpp').read_text(encoding='utf-8')
        for row in exe_texts.contracts()['records']:
            self.assertIn('{'+str(row['id'])+','+row['patch_va']+','+row['source_va']+',"'+row['source']+'"}',text)
            self.assertEqual(row['max_bytes'],64)
