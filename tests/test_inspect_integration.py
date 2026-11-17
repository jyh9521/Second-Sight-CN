import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import inspect_integration as audit


class IntegrationFootprints(unittest.TestCase):
    source=b'synthetic source identity for footprint tests'

    def row(self,index=0):
        pattern=list(audit.CUTSCENE_WRITES)[index]
        address,_=audit.CUTSCENE_WRITES[pattern]
        return dict(source='Cutscenes.ixx',pattern=pattern,expected_address=hex(address))

    def narrowed(self,index=0):
        with patch.object(audit,'CUTSCENES_SHA256',hashlib.sha256(self.source).hexdigest()):
            return audit.write_envelopes(self.row(index),self.source)

    def test_actual_cutscene_writes_exclude_subtitle_call(self):
        writes=self.narrowed()+self.narrowed(1)
        self.assertEqual(writes,[(0x542fe0,6),(0x542fea,4),(0x543017,4)])
        audit.require_disjoint(writes,[(0x543031,5),(0x5431e8,6)])

    def test_each_actual_write_still_blocks_overlap(self):
        for start,size in self.narrowed()+self.narrowed(1):
            for address in (start,start+size-1):
                with self.assertRaisesRegex(ValueError,'overlap'):
                    audit.require_disjoint([(start,size)],[(address,1)])

    def test_changed_source_rejected(self):
        with self.assertRaisesRegex(ValueError,'source identity changed'):
            audit.write_envelopes(self.row(),self.source)

    def test_changed_address_rejected(self):
        row=self.row();row['expected_address']='0x543000'
        with patch.object(audit,'CUTSCENES_SHA256',hashlib.sha256(self.source).hexdigest()):
            with self.assertRaisesRegex(ValueError,'address changed'):
                audit.write_envelopes(row,self.source)

    def test_other_patterns_remain_conservative(self):
        row=dict(source='Hud.ixx',pattern='test',expected_address='0x1000')
        self.assertEqual(audit.write_envelopes(row,b''),[(0x1000,96)])
        with self.assertRaisesRegex(ValueError,'overlap'):
            audit.require_disjoint(audit.write_envelopes(row,b''),[(0x105f,1)])

    def test_touching_boundaries_are_disjoint(self):
        audit.require_disjoint([(0x1000,6)],[(0xfff,1),(0x1006,1)])


if __name__=='__main__':unittest.main()
