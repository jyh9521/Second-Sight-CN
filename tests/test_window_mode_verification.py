"""Synthetic config-only rollback tests; no proprietary files or DLL loads."""
import contextlib
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import stage_poc as stage
import verify_window_mode as verify


class WindowModeVerificationTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.source=self.root/"source.cfg"
        self.original=b"[MAIN]\r\nWindowMode = 0\r\nFPSLimit = -1\r\n"
        self.modified=self.original.replace(b"WindowMode = 0",b"WindowMode = 2")
        self.source.write_bytes(self.original)
        sha=lambda data:hashlib.sha256(data).hexdigest()
        for mock in (patch.dict(stage.FUSION_FILES,{stage.FUSION_CONFIG_PATH:sha(self.original)}),
                     patch.object(stage,"BORDERLESS_CONFIG_SHA",sha(self.modified)),
                     patch.object(verify,"BORDERLESS_CONFIG_SHA",sha(self.modified))):
            mock.start();self.addCleanup(mock.stop)
        redirect=contextlib.redirect_stdout(io.StringIO());redirect.__enter__()
        self.addCleanup(redirect.__exit__,None,None,None)

    def test_prepare_probe_rollback_and_modified_retention(self):
        out=self.root/"evidence"
        verify.prepare(self.source,out)
        self.assertEqual(verify.probe(out/"BASELINE.cfg"),2)
        self.assertEqual(verify.probe(out/"MODIFIED_FILE.cfg"),0)
        verify.rollback(out)
        self.assertEqual((out/"ROLLBACK_TEST.cfg").read_bytes(),self.original)
        self.assertEqual((out/"MODIFIED_FILE.cfg").read_bytes(),self.modified)
        self.assertEqual(self.source.read_bytes(),self.original)
        with self.assertRaises(ValueError):verify.rollback(out)
        with self.assertRaises(ValueError):verify.prepare(self.source,out)

    def test_unknown_source_rejected_without_output(self):
        self.source.write_bytes(b"unknown")
        out=self.root/"evidence"
        with self.assertRaises(ValueError):verify.prepare(self.source,out)
        with self.assertRaises(ValueError):verify.probe(self.source)
        self.assertFalse(out.exists())

    @unittest.skipUnless(os.name=="nt","Windows cross-volume paths")
    def test_other_drive_uses_absolute_tool_reference(self):
        drive="Y:/" if self.root.drive.upper()=="Z:" else "Z:/"
        other=Path(drive)/"synthetic repository"
        out=self.root/"cross-volume"
        with patch.object(verify,"ROOT",other):verify.prepare(self.source,out)
        script=(out/"ROLLBACK.sh").read_text()
        self.assertIn((other/"tools/verify_window_mode.py").as_posix(),script)
        self.assertEqual(self.source.read_bytes(),self.original)

    def test_tampered_rollback_target_rejected_without_overwrite(self):
        out=self.root/"evidence";verify.prepare(self.source,out)
        target=out/"ROLLBACK_TEST.cfg";target.write_bytes(b"changed by somebody else")
        with self.assertRaises(ValueError):verify.rollback(out)
        self.assertEqual(target.read_bytes(),b"changed by somebody else")


if __name__=="__main__":unittest.main()
