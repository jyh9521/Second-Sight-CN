import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from package_retention import preserve_user_files

class UserFiles(unittest.TestCase):
    def test_keep_savedata_settings_logs_not_game_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); old=root/"dist/poc-zh-CN-006"
            expected={"game/profiles/user.sav":b"save", "game/scripts/fix.cfg":b"changed cfg",
                      "game/DSOUND.log":b"log", "game/dsound.ini":b"ini"}
            for name,data in {**expected,"game/textures.dds":b"asset"}.items():
                file=old/name; file.parent.mkdir(parents=True,exist_ok=True); file.write_bytes(data)
            plan={"root":str(old.parent),"remove":[{"path":str(old),"name":old.name}]}
            backup=root/"evidence/users"
            result=preserve_user_files(plan,backup)
            self.assertEqual(result,{f"{old.name}/{name}":hashlib.sha256(data).hexdigest() for name,data in expected.items()})
            self.assertTrue((old/"game/profiles/user.sav").exists())
            self.assertFalse((backup/old.name/"game/textures.dds").exists())
            self.assertEqual(preserve_user_files(plan,backup),result)
            (old/"game/profiles/user.sav").write_bytes(b"different save")
            with self.assertRaisesRegex(ValueError,"backup differs"): preserve_user_files(plan,backup)

    def test_reject_backup_inside_removed_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            old=Path(temporary)/"dist/poc-zh-CN-006"; old.mkdir(parents=True)
            plan={"root":str(old.parent),"remove":[{"path":str(old),"name":old.name}]}
            with self.assertRaisesRegex(ValueError,"inside deletion"): preserve_user_files(plan,old/"backup")

if __name__=="__main__": unittest.main()
