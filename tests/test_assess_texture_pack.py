from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from assess_texture_pack import dds_metadata


def fixture(width=4,height=4,mips=1,fmt=b"DXT1",payload=8):
    data=bytearray(128+payload);data[:4]=b"DDS "
    for offset,value in ((4,124),(12,height),(16,width),(28,mips),(76,32),(80,4)):
        struct.pack_into("<I",data,offset,value)
    data[84:88]=fmt
    return bytes(data)


class TextureTests(unittest.TestCase):
    def test_simple_and_non_block_multiple(self):
        self.assertEqual(dds_metadata(fixture())["mip_payload_bytes"],8)
        self.assertEqual(dds_metadata(fixture(5,5,payload=32))["mip_payload_bytes"],32)
    def test_mips_have_minimum_one_block(self):
        self.assertEqual(dds_metadata(fixture(mips=3,payload=24))["mip_payload_bytes"],24)
    def test_truncated(self):
        for raw in (b"DDS ",fixture()[:-1]):
            with self.assertRaises(ValueError): dds_metadata(raw)
    def test_unsupported_format(self):
        with self.assertRaises(ValueError): dds_metadata(fixture(fmt=b"DX10"))
    def test_bad_dimensions_and_mips(self):
        for raw in (fixture(width=0),fixture(mips=4,payload=32)):
            with self.assertRaises(ValueError): dds_metadata(raw)
    def test_trailing_reported_not_silently_discarded(self):
        self.assertEqual(dds_metadata(fixture()+b"tail")["trailing_bytes"],4)
    def test_dxt5_and_depth_rejection(self):
        self.assertEqual(dds_metadata(fixture(fmt=b"DXT5",payload=16))["mip_payload_bytes"],16)
        data=bytearray(fixture());struct.pack_into("<I",data,24,4)
        with self.assertRaises(ValueError):dds_metadata(bytes(data))


if __name__=="__main__":unittest.main()
