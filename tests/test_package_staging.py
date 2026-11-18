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

    def test_tweaks_must_stage_outside_the_loader_tree(self):
        data=self.record(True)
        data["gameplay_tweaks"]="optional-disabled-v1"
        data["files"]["Set-GameplayTweaks.ps1"]="script"
        for name in stage.TWEAKS_FILES:
            data["files"][f"{stage.TWEAKS_DIR}/{name}"]="digest"
        stage.validate_layout(data)
        data["gameplay_tweaks"]=stage.TWEAKS_DEFAULT
        stage.validate_layout(data)
        for name in stage.TWEAKS_FILES:
            invalid=copy.deepcopy(data)
            invalid["files"]["game/scripts/"+name]="digest"
            with self.assertRaisesRegex(ValueError,"outside the game"):
                stage.validate_layout(invalid)
            del invalid["files"][f"{stage.TWEAKS_DIR}/{name}"]
            with self.assertRaisesRegex(ValueError,"outside the game"):
                stage.validate_layout(invalid)

    def test_new_packages_install_tweaks_and_keep_a_toggleable_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            out=root/"package"
            active=out/"game/scripts"
            active.mkdir(parents=True)
            binary=root/"module.asi"
            binary.write_bytes(b"synthetic optional module")
            labels=root/"labels.ini"
            labels.write_text("[Menu]\nTitle=Sample\n",encoding="utf-8")
            stage.stage_gameplay_tweaks(out,binary,labels)
            files=stage.package_files(out)
            self.assertTrue(stage.verify_tweaks(out,files))
            self.assertEqual((active/stage.TWEAKS_FILES[0]).read_text(encoding="utf-16"),labels.read_text(encoding="utf-8"))
            for name in stage.TWEAKS_FILES:
                self.assertNotIn("game/scripts/"+name,files)
                self.assertEqual(files[stage.TWEAKS_DIR+"/"+name],stage.sha(active/name))
                (active/name).unlink()
            self.assertFalse(stage.verify_tweaks(out,files))

    def test_imported_fusionfix_config_is_recorded_but_binary_remains_pinned(self):
        data=self.record(True)
        data.update(package_id="poc-zh-CN-012",version=12,fusionfix_config=stage.fusionfix_config_record())
        config_hash="1"*64
        data["local_fusionfix_config"]={"from_package":"poc-zh-CN-011","sha256":config_hash}
        data["files"]["game/"+stage.FUSION_CONFIG_PATH]=config_hash
        stage.validate_layout(data)
        for key,value in (("from_package","poc-zh-CN-012"),("sha256",None)):
            invalid=copy.deepcopy(data)
            invalid["local_fusionfix_config"][key]=value
            with self.assertRaisesRegex(ValueError,"local FusionFix"):
                stage.validate_layout(invalid)
        data["files"]["game/scripts/SecondSight.FusionFix.asi"]=config_hash
        with self.assertRaisesRegex(ValueError,"FusionFix identity"):
            stage.validate_layout(data)

    @unittest.skipUnless(os.name=="nt","test the Windows installation and rollback script")
    def test_optional_script_roundtrip_and_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            active=root/"game/scripts"; active.mkdir(parents=True)
            stored=root/stage.TWEAKS_DIR; stored.mkdir(parents=True)
            keep=active/"SecondSight.FusionFix.asi"
            keep.write_bytes(b"synthetic unrelated FusionFix")
            files={}
            for i,name in enumerate(stage.TWEAKS_FILES):
                (stored/name).write_bytes(f"synthetic module asset {i}".encode())
                files[f"{stage.TWEAKS_DIR}/{name}"]=stage.sha(stored/name)
            (root/"package.json").write_text(json.dumps({"files":files}),encoding="utf-8")
            script=root/"Set-GameplayTweaks.ps1"
            shutil.copy2(stage.ROOT/"tools"/script.name,script)
            def run(mode):
                return subprocess.run(["powershell","-NoProfile","-ExecutionPolicy","Bypass",
                                       "-File",str(script),"-Mode",mode],capture_output=True)
            before=stage.inventory(root)
            result=run("Status")
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn(b"disabled",result.stdout)
            for mode in ("Enable","Enable","Status"):
                result=run(mode)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIn(b"enabled",result.stdout)
            conflict=active/stage.TWEAKS_FILES[1]
            conflict.write_bytes(b"unknown user file")
            self.assertNotEqual(run("Disable").returncode,0)
            self.assertEqual(conflict.read_bytes(),b"unknown user file")
            shutil.copy2(stored/conflict.name,conflict)
            result=run("Disable")
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn(b"disabled",result.stdout)
            self.assertEqual(stage.inventory(root),before)

    def test_new_package_requires_pinned_borderless_override(self):
        for hd in (False, True):
            data=self.record(hd)
            data.update(package_id="poc-zh-CN-004",version=4)
            with self.assertRaisesRegex(ValueError,"borderless"):
                stage.validate_layout(data)
            data['fusionfix_config']=stage.fusionfix_config_record()
            data['files']['game/'+stage.FUSION_CONFIG_PATH]=stage.BORDERLESS_CONFIG_SHA
            stage.validate_layout(data)
            for field,value in (("source_sha256","wrong"),("output_sha256","wrong"),
                                ("overrides",{"MAIN.WindowMode":0}),("policy","unknown")):
                altered=copy.deepcopy(data);altered['fusionfix_config'][field]=value
                with self.assertRaisesRegex(ValueError,"borderless"):
                    stage.validate_layout(altered)
            data['files']['game/'+stage.FUSION_CONFIG_PATH]=stage.FUSION_FILES[stage.FUSION_CONFIG_PATH]
            with self.assertRaises(ValueError): stage.validate_layout(data)

    def test_startup_adapter_requires_explicit_preload(self):
        for hd in (False,True):
            data=self.record(hd);data['startup_compat']='gog-fusionfix-contracts-v1'
            data['files']['game/scripts/SecondSight.Compatibility.asi']='own-adapter'
            with self.assertRaises(ValueError):stage.validate_layout(data)
            ini='game/'+data['loader'].replace('.dll','.ini')
            data['files'][ini]=hashlib.sha256(stage.COMPAT_LOADER_INI.encode()).hexdigest()
            stage.validate_layout(data)
            del data['files']['game/scripts/SecondSight.Compatibility.asi']
            with self.assertRaises(ValueError):stage.validate_layout(data)

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
            (root/"alias-parent").mkdir()
            # Exercise equivalent lexical/canonical roots (also covers CI's short TEMP path).
            with patch.object(integration,"ROOT",root/"alias-parent"/".."),contextlib.redirect_stdout(io.StringIO()):
                integration.prepare(out,*packages)
            self.assertEqual((out/"MODIFIED_FILE.json").read_bytes(),(packages[1]/"package.json").read_bytes())
            self.assertIn("../../..",(out/"ROLLBACK.sh").read_text())


class RemasteredQuarantineTests(unittest.TestCase):
    def test_pinned_inventory_reconstructed_only_from_inactive_verified_dds(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            game=out/"game"
            active=game/"Remaster_Textures"
            active.mkdir(parents=True)
            keep="tex_12345678.dds"
            removed="tex_5D6828F8.dds"
            depot=out/stage.REMASTER_QUARANTINE_DIR
            depot.mkdir(parents=True)
            (game/"dinput8.dll").write_bytes(b"synthetic proxy")
            (active/keep).write_bytes(b"active")
            (depot/removed).write_bytes(b"inactive with source bytes")
            hashes=stage.inventory(out)
            record={"version":13,"files":hashes,"remastered":{"fallback_policy":stage.REMASTER_POLICY}}
            expected={
                "dinput8.dll":hashes["game/dinput8.dll"],
                f"Remaster_Textures/{keep}":hashes[f"game/Remaster_Textures/{keep}"],
                f"Remaster_Textures/{removed}":hashes[f"{stage.REMASTER_QUARANTINE_DIR}/{removed}"],
            }
            with patch.object(stage,"REMASTER_QUARANTINE",{removed:expected[f"Remaster_Textures/{removed}"]}), \
                 patch.object(stage,"remastered_inventory") as reconcile,contextlib.redirect_stdout(io.StringIO()):
                stage.verify_hd(out,record)
                reconcile.assert_called_once_with(game,expected,{f"Remaster_Textures/{removed}":depot/removed})
                # DLL falls back to PNG after missing DDS, so verify both forms.
                for identity in (removed,Path(removed).with_suffix(".png").name):
                    leftover=active/identity
                    leftover.write_bytes(b"unlisted replacement")
                    with self.assertRaisesRegex(ValueError,"unexpected active"):
                        stage.verify_hd(out,record)
                    leftover.unlink()
                changed=copy.deepcopy(record)
                changed["files"][f"{stage.REMASTER_QUARANTINE_DIR}/{removed}"]="0"*64
                with self.assertRaisesRegex(ValueError,"quarantine entry"):
                    stage.verify_hd(out,changed)


class BorderlessConfigTests(unittest.TestCase):
    def test_only_main_window_mode_byte_changes(self):
        for newline in (b'\n',b'\r\n'):
            source=newline.join((b'; WindowMode = 0',b'[MAIN]',b'WindowMode = 0 ; original',
                                 b'FPSLimit = -1',b'[OTHER]',b'WindowMode = 1',b''))
            result=stage.borderless_config(source)
            self.assertEqual(result,source.replace(b'WindowMode = 0 ; original',b'WindowMode = 2 ; original'))
            self.assertEqual(sum(a!=b for a,b in zip(source,result)),1)

    def test_case_whitespace_and_no_final_newline(self):
        self.assertEqual(stage.borderless_config(b'[main]\n  windowmode\t= 1'),b'[main]\n  windowmode\t= 2')
        source=b'[MAIN]\nWindowMode=2'
        self.assertEqual(stage.borderless_config(source),source)

    def test_missing_duplicate_and_invalid_modes_rejected(self):
        for source in (b'[OTHER]\nWindowMode=0',b'[MAIN]\n;WindowMode=0',
                       b'[MAIN]\nWindowMode=0\nWindowMode=1',
                       b'[MAIN]\nWindowMode=0\n[MAIN]\nX=1',
                       b'[MAIN]\nWindowMode=3',b'[MAIN]\nWindowMode=00',
                       b'[MAIN]\nWindowMode=0 garbage'):
            with self.subTest(source=source),self.assertRaises(ValueError):
                stage.borderless_config(source)

    def test_writer_preserves_input_and_records_both_hashes(self):
        source=b'[MAIN]\r\nWindowMode = 0\r\nFPSLimit = -1\r\n'
        output=source.replace(b'WindowMode = 0',b'WindowMode = 2')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);original=root/'input.cfg';target=root/'output.cfg'
            original.write_bytes(source)
            with patch.dict(stage.FUSION_FILES,{stage.FUSION_CONFIG_PATH:hashlib.sha256(source).hexdigest()}), \
                 patch.object(stage,'BORDERLESS_CONFIG_SHA',hashlib.sha256(output).hexdigest()):
                record=stage.write_fusionfix_config(original,target)
                self.assertEqual(original.read_bytes(),source)
                self.assertEqual(target.read_bytes(),output)
                self.assertEqual(record,stage.fusionfix_config_record())
                self.assertEqual(record['overrides'],{'MAIN.WindowMode':2})
                with self.assertRaises(FileExistsError):stage.write_fusionfix_config(original,target)

    def test_wrong_source_rejected_before_output_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);original=root/'input.cfg';target=root/'output.cfg'
            original.write_bytes(b'[MAIN]\nWindowMode=0')
            with self.assertRaisesRegex(ValueError,'input'):
                stage.write_fusionfix_config(original,target)
            self.assertFalse(target.exists())


if __name__=="__main__": unittest.main()
