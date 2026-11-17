"""Synthetic packaging tests; no game, mod binaries or graphics APIs are used."""
import copy
import contextlib
import hashlib
import json
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import package_retention as retention
import stage_poc as stage
import verify_integration as integration


def marker(root, name, version=None):
    directory=root/name
    (directory/"game").mkdir(parents=True)
    (directory/"game/secondsight.EXE").write_bytes(b"synthetic-not-an-executable")
    data=dict(format="second-sight-local-test-v1",status="awaiting-user-runtime-test",
              files={"game/secondsight.EXE":stage.sha(directory/"game/secondsight.EXE")})
    if version is not None:
        data.update(format="second-sight-local-test-v2",version=version,package_id=name)
    (directory/"package.json").write_text(json.dumps(data),encoding="utf-8")
    return directory


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.dist=self.root/"dist"
        self.dist.mkdir()

    def test_sequences(self):
        self.assertEqual(retention.sequence("poc-zh-CN"),0)
        self.assertEqual(retention.sequence("poc-ja-JP-002"),2)
        self.assertEqual(retention.sequence("poc-en-1000"),1000)
        self.assertIsNone(retention.sequence("research-20261117"))

    def test_keep_newest_two_by_sequence_not_mtime(self):
        old=marker(self.dist,"poc-zh-CN")
        marker(self.dist,"poc-zh-CN-001")
        new=marker(self.dist,"poc-zh-CN-002",2)
        os.utime(old,(2000000000,2000000000))
        plan=retention.plan_retention(self.dist,new)
        self.assertEqual([r["name"] for r in plan["keep"]],["poc-zh-CN-002","poc-zh-CN-001"])
        self.assertEqual([r["name"] for r in plan["remove"]],["poc-zh-CN"])
        self.assertTrue(old.exists()) # planning is read-only

    def test_unknown_and_incomplete_are_not_deletion_candidates(self):
        (self.dist/"poc-zh-CN-000").mkdir()
        marker(self.dist,"research-000")
        wrong=marker(self.dist,"poc-zh-CN-001",7)
        new=marker(self.dist,"poc-zh-CN-002",2)
        plan=retention.plan_retention(self.dist,new)
        self.assertEqual(len(plan["keep"]),1)
        self.assertEqual(plan["remove"],[])
        self.assertTrue(wrong.exists())

    def test_nonnewest_and_outside_rejected(self):
        old=marker(self.dist,"poc-zh-CN-001",1)
        marker(self.dist,"poc-zh-CN-002",2)
        with self.assertRaisesRegex(ValueError,"newest"):
            retention.plan_retention(self.dist,old)
        with self.assertRaisesRegex(ValueError,"direct child"):
            retention.plan_retention(self.dist,self.root)

    def test_duplicate_sequences_rejected(self):
        marker(self.dist,"poc-zh-CN-002",2)
        marker(self.dist,"poc-ja-JP-002",2)
        with self.assertRaisesRegex(ValueError,"duplicate"):
            retention.candidates(self.dist)

    def test_linked_root_rejected_before_resolve(self):
        new=marker(self.dist,"poc-zh-CN-002",2)
        with patch.object(retention,"is_link",return_value=True):
            with self.assertRaisesRegex(ValueError,"linked"):
                retention.plan_retention(self.dist,new)

    def test_output_must_be_numbered_new_and_inside_dist(self):
        with patch.object(stage,"ROOT",self.root):
            self.assertEqual(stage.validate_output(self.dist/"poc-zh-CN-002","zh-CN"),2)
            for invalid in (self.root/"poc-zh-CN-002",self.dist/"arbitrary",self.dist/"poc-ja-JP-002"):
                with self.assertRaises(ValueError): stage.validate_output(invalid,"zh-CN")
            marker(self.dist,"poc-zh-CN-003",3)
            with self.assertRaises(ValueError): stage.validate_output(self.dist/"poc-zh-CN-002","zh-CN")

    @unittest.skipUnless(os.name=="nt","native Windows retention executor")
    def test_powershell_retention_and_stale_manifest(self):
        (self.root/"tools").mkdir()
        shutil.copy2(stage.ROOT/"tools/prune_test_packages.ps1",self.root/"tools/prune_test_packages.ps1")
        old=marker(self.dist,"poc-zh-CN")
        kept=marker(self.dist,"poc-zh-CN-001")
        new=marker(self.dist,"poc-zh-CN-002",2)
        unknown=self.dist/"notes"; unknown.mkdir()
        plan=retention.plan_retention(self.dist,new)
        path=self.root/"plan.json"; path.write_text(json.dumps(plan))
        command=["powershell","-NoProfile","-ExecutionPolicy","Bypass","-File",
                 str(self.root/"tools/prune_test_packages.ps1"),"-Plan",str(path)]
        original=(old/"package.json").read_bytes()
        (old/"package.json").write_bytes(original+b" ")
        result=subprocess.run(command,capture_output=True)
        self.assertNotEqual(result.returncode,0)
        self.assertTrue(old.exists())
        (old/"package.json").write_bytes(original)
        result=subprocess.run(command,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(old.exists())
        self.assertTrue(kept.exists() and new.exists() and unknown.exists())


class LayoutTests(unittest.TestCase):
    def record(self,hd):
        files={"game/secondsight.EXE":stage.EXE_SHA,
               "game/scripts/SecondSight.Localization.asi":"own-module-hash",
               "game/scripts/localization/locale.bin":"own-pack-hash"}
        for name,value in stage.FUSION_FILES.items():
            files["game/"+("dsound.dll" if hd and name=="dinput8.dll" else name)]=value
        if hd:
            files["game/dinput8.dll"]=stage.REMASTER_DLL_SHA
            files["game/dsound.ini"]=hashlib.sha256(stage.LOADER_INI.encode()).hexdigest()
        return dict(format="second-sight-local-test-v2",status="awaiting-user-runtime-test",
                    package_id="poc-zh-CN-002",version=2,loader="dsound.dll" if hd else "dinput8.dll",
                    remastered={"inventory_sha256":stage.REMASTER_INVENTORY_SHA} if hd else None,files=files)

    def test_both_layouts(self):
        for hd in (False,True): stage.validate_layout(self.record(hd))

    def test_legacy_compatible(self):
        data=self.record(False); data["format"]="second-sight-local-test-v1"
        del data["loader"]
        stage.validate_layout(data)

    def test_missing_or_swapped_loaders_rejected(self):
        original=self.record(True)
        for name in ("game/dinput8.dll","game/dsound.dll","game/dsound.ini",
                     "game/scripts/SecondSight.FusionFix.asi","game/scripts/SecondSight.Localization.asi",
                     "game/scripts/localization/locale.bin"):
            data=copy.deepcopy(original); del data["files"][name]
            with self.assertRaises(ValueError): stage.validate_layout(data)
        data=copy.deepcopy(original)
        data["files"]["game/dinput8.dll"]=stage.FUSION_FILES["dinput8.dll"]
        with self.assertRaises(ValueError): stage.validate_layout(data)

    def test_wrong_loader_or_pack_identity_rejected(self):
        for key,value in (("loader","version.dll"),("version",99),("status","complete")):
            data=self.record(True); data[key]=value
            with self.assertRaises(ValueError): stage.validate_layout(data)
        data=self.record(True); data["remastered"]["inventory_sha256"]="different"
        with self.assertRaises(ValueError): stage.validate_layout(data)

    def test_incomplete_hd_input_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,"5110"):
                stage.remastered_inventory(Path(directory))

    def test_manifest_escape_rejected_without_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ("../outside","C:/outside","game/../../outside"):
                data={"files":{name:"hash"}}
                (root/"package.json").write_text(json.dumps(data))
                with patch.object(stage,"validate_layout"):
                    with self.assertRaisesRegex(ValueError,"manifest path"):
                        stage.verify(root)

    def test_snapshot_preserves_manifest_newlines_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            packages=[]
            for number,hd in ((1,False),(2,True)):
                package=root/"dist"/f"poc-zh-CN-{number:03d}"
                record=self.record(hd)
                for name in integration.COPY_FILES:
                    path=package/name;path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_bytes(b"synthetic-only")
                (package/"package.json").write_text(json.dumps(record)+"\n",encoding="utf-8",newline="\n")
                packages.append(package)
            out=root/"build/nested/evidence"
            with patch.object(integration,"ROOT",root),contextlib.redirect_stdout(io.StringIO()):
                integration.prepare(out,*packages)
            self.assertEqual((out/"MODIFIED_FILE.json").read_bytes(),(packages[1]/"package.json").read_bytes())
            self.assertIn("../../..",(out/"ROLLBACK.sh").read_text())


if __name__=="__main__": unittest.main()
