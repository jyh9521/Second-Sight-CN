import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from audit_locale_policy import audit_text, audit, visible_text
from check_docs import check_tree
from inventory_inputs import inventory
from locale_policies import check_locale as generic_check
from locale_policies.zh_sentence_endings import analyze
from translation_checks import check_data
import build_locale


class SentenceRegressions(unittest.TestCase):
    def test_completed_sentence_comma_does_not_leak(self):
        self.assertEqual([f['index'] for f in audit_text('zh-CN','保存完成，请继续。按键返回。','other')],[13])

    def test_layout_and_ellipsis_preserve_comma(self):
        for text in ['保存完成，\n请继续。','保存完成，请稍候……然后继续。','请确认，选择“成功！”按钮。']:
            self.assertEqual(audit_text('zh-CN',text,'other'),[])

    def test_nested_period_is_independent(self):
        self.assertEqual(len(audit_text('zh-CN','请确认，选择“保存成功。”按钮。','other')),1)

    def test_colon_semicolon_not_commas(self):
        for text in ['提示：按键返回。','提高攻击力；持续十秒。','「保存成功。」']:
            self.assertEqual(len(audit_text('zh-CN',text,'other')),1)

    def test_ambiguous_dots_quotes_and_markup_are_review(self):
        for text in ['数值为 3.','例如 e.g.','名称 Mr.','请确认，选择“成功。','<color=255,0,0>成功。</color>']:
            self.assertTrue(any(f['kind']=='review' for f in audit_text('zh-CN',text,'other')))

    def test_no_deletion_of_non_sentence_dots(self):
        for text in ['版本 1.2.3','打开 save.dat','是否覆盖？','正在加载...','正在加载……']:
            self.assertEqual(audit_text('zh-CN',text,'other'),[])

    def test_verified_native_tokens_preserve_original_offsets(self):
        text='按\x0b2继续。按%1返回。'
        visible, positions=visible_text(text)
        self.assertEqual(visible,'按\ufffc继续。按\ufffc返回。')
        self.assertEqual([f['index'] for f in audit_text('zh-CN',text,'other')],[5,11])
        self.assertEqual([text[positions[i]] for i,c in enumerate(visible) if c=='。'],['。','。'])

    def test_unknown_control_and_role_rejected(self):
        with self.assertRaises(ValueError):audit_text('zh-CN','\x01提示','other')
        with self.assertRaises(ValueError):audit_text('zh-CN','提示。','unknown')

    def test_narrative_and_other_locale_not_chineseized(self):
        self.assertEqual(audit_text('zh-CN','故事。人物说话。','story_or_dialogue'),[])
        self.assertEqual(generic_check('en-US',{'id':'x','text_role':'other','target':'Done.'}),[])
        with self.assertRaises(ValueError):audit_text('en-US','Done.','other')

    def test_audit_does_not_mutate_catalog(self):
        files=list((ROOT/'locales/zh-CN').glob('*.json'))
        before={p:p.read_bytes() for p in files}
        report=audit(ROOT/'locales/zh-CN')
        self.assertEqual(len(report['findings']),51)
        self.assertEqual(report['status'],'fail')
        self.assertEqual(before,{p:p.read_bytes() for p in files})

    def test_build_stops_before_resource_processing(self):
        with tempfile.TemporaryDirectory() as folder:
            game=Path(folder)/'input';game.mkdir();(game/'secondsight.exe').write_bytes(b'synthetic')
            output=Path(folder)/'output'
            with patch.object(build_locale,'digest',return_value=build_locale.EXE_SHA), patch.object(build_locale,'dependency') as fetch:
                with self.assertRaisesRegex(ValueError,'editorial checks failed'):
                    build_locale.build(game,'zh-CN',output)
                fetch.assert_not_called()
            self.assertFalse(output.exists())


class InfrastructureRegressions(unittest.TestCase):
    def test_inventory_has_exact_hash_and_leaves_input(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'a.dat').write_bytes(b'abc')
            result=inventory(root,'synthetic','unknown','1','fixture')
            self.assertEqual(result['files'],[dict(path='a.dat',bytes=3,sha256='ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',role='fixture')])
            self.assertEqual((root/'a.dat').read_bytes(),b'abc')
            self.assertEqual(result['status'],'inventory_only_not_G0_acceptance')

    def test_doc_links_exact_case_and_anchors(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'Guide.md').write_text('# Heading',encoding='utf8')
            main=root/'README.md';main.write_text('[Guide](Guide.md#heading)',encoding='utf8')
            self.assertEqual(check_tree(root)[1],[])
            main.write_text('[Guide](guide.md#heading)',encoding='utf8')
            self.assertTrue(check_tree(root)[1])
            main.write_text('[Guide](Guide.md#missing)',encoding='utf8')
            self.assertTrue(check_tree(root)[1])


if __name__=='__main__':unittest.main()
