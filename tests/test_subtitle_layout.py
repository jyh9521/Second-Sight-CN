from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from replay_subtitle_layout import map_exact, replay, validate_options


class SubtitleReplayValidation(unittest.TestCase):
    def test_invalid_combinations_rejected_before_input(self):
        for options in [(None,'map',False,False,False),
                        (None,None,True,False,False),
                        ('asi','map',False,True,False),
                        (None,None,False,False,True),
                        ('asi',None,False,False,True),
                        ('asi','map',True,False,True)]:
            with self.subTest(options=options):
                with self.assertRaises(ValueError):validate_options(*options)

    def test_valid_modes(self):
        for options in [(None,None,False,False,False),
                        (None,None,False,True,False),
                        ('asi','map',False,False,False),
                        ('asi','map',False,False,True),
                        ('asi','map',True,False,False)]:
            validate_options(*options)

    def test_map_exact_name_and_unique_address(self):
        text='0001:00000001 _malloc 10001000\n0001:00000002 __malloc_base 10002000\n'
        self.assertEqual(map_exact(text,'__malloc_base'),0x10002000)
        with self.assertRaises(ValueError):map_exact(text,'malloc')
        with self.assertRaises(ValueError):
            map_exact(text+'0001:00000003 __malloc_base 10003000\n','__malloc_base')

    def test_unknown_executable_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'fixture.exe';before=b'not the supported proprietary input';p.write_bytes(before)
            with self.assertRaisesRegex(ValueError,'unsupported executable identity'):
                replay(p,640,480,7)
            self.assertEqual(p.read_bytes(),before)


if __name__=='__main__':unittest.main()
