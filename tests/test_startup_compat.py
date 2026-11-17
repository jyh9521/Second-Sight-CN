import struct
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import startup_compat as compat
from minidump_reader import Minidump


class StartupContracts(unittest.TestCase):
    def fixture(self):
        data=bytearray(0x184000)
        for row in compat.sites(): data[row['rva']:row['rva']+len(row['before'])]=row['before']
        return bytes(data)

    def test_four_sites_roundtrip(self):
        before=self.fixture();after=compat.transform(before)
        self.assertNotEqual(before,after)
        self.assertEqual(compat.transform(after,True),before)
        self.assertEqual(sum(len(row['before']) for row in compat.sites()),22)

    def test_only_declared_bytes_changed(self):
        before=self.fixture();after=compat.transform(before)
        allowed={i for row in compat.sites() for i in range(row['rva'],row['rva']+len(row['before']))}
        self.assertTrue(all(a==b or i in allowed for i,(a,b) in enumerate(zip(before,after))))

    def test_any_site_conflict_rejects_whole_transform(self):
        for row in compat.sites():
            bad=bytearray(self.fixture());bad[row['rva']]^=1;before=bytes(bad)
            with self.assertRaises(ValueError):compat.transform(before)
            self.assertEqual(bytes(bad),before)

    def test_already_modified_rejected(self):
        with self.assertRaises(ValueError):compat.transform(compat.transform(self.fixture()))

    def test_short_input_rejected(self):
        with self.assertRaises(ValueError):compat.transform(b'')

    def test_overlay_is_separate_owned_storage(self):
        row=compat.sites(0x12345678)[3]
        self.assertEqual(row['after'],bytes.fromhex('d8 0d 78 56 34 12'))
        for pointer in (0,-1,2**32):
            with self.assertRaises(ValueError):compat.sites(pointer)


class RecordedDumpTests(unittest.TestCase):
    def parse(self,data):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'fixture.dmp';path.write_bytes(data);return Minidump(path)

    def test_bad_magic(self):
        with self.assertRaises(ValueError):self.parse(b'not a dump')

    def test_bad_directory_bounds(self):
        data=bytearray(32);data[:4]=b'MDMP';struct.pack_into('<II',data,8,2,32)
        with self.assertRaises(ValueError):self.parse(data)

    def test_repeated_unused_streams_allowed(self):
        data=bytearray(56);data[:4]=b'MDMP';struct.pack_into('<II',data,8,2,32)
        self.assertEqual(self.parse(data).streams,{})

    def test_duplicate_real_stream_rejected(self):
        data=bytearray(56);data[:4]=b'MDMP';struct.pack_into('<II',data,8,2,32)
        struct.pack_into('<III',data,32,7,0,56);struct.pack_into('<III',data,44,7,0,56)
        with self.assertRaises(ValueError):self.parse(data)

    def test_missing_recorded_memory_stays_unknown(self):
        data=bytearray(32);data[:4]=b'MDMP'
        with self.assertRaisesRegex(ValueError,'not recorded'):self.parse(data).read(0x400000,1)

    def test_memory_list_read_spans_adjacent_ranges(self):
        data=bytearray(88);data[:4]=b'MDMP';struct.pack_into('<II',data,8,1,32)
        struct.pack_into('<III',data,32,5,36,44);struct.pack_into('<I',data,44,2)
        struct.pack_into('<QII',data,48,0x1000,4,80);struct.pack_into('<QII',data,64,0x1004,4,84)
        data[80:]=b'abcdefgh'
        self.assertEqual(self.parse(data).read(0x1002,5),b'cdefg')


if __name__=='__main__':unittest.main()
