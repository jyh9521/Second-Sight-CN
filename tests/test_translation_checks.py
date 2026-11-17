import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from translation_checks import needs_full_stop_removal,check_data,check_locale


class EditorialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy=json.loads((ROOT/'locales/zh-CN/style.json').read_text(encoding='utf-8'))

    def test_simple_ui_objective_stop_is_rejected(self):
        for text in ['逃离。','离开隔离室。','保存成功.','“已完成。”','版本 1.2 已安装。']:
            for kind in ['ui','objective']:
                with self.subTest(text=text,kind=kind):
                    self.assertTrue(needs_full_stop_removal(text,kind,self.policy['punctuation']))

    def test_commas_multi_sentence_and_other_marks_preserved(self):
        for text in ['离开隔离室','打开背包，选择物品。','取得钥匙、文件。','先开门,再离开。',
                     '先开门。再离开。','确定吗？请确认。','存档成功！','要退出吗？','正在保存……','正在保存...']:
            with self.subTest(text=text):
                self.assertFalse(needs_full_stop_removal(text,'objective',self.policy['punctuation']))

    def test_narrative_exempt_in_any_resource(self):
        for text in ['让我帮你。','他必须设法逃离。']:
            self.assertFalse(needs_full_stop_removal(text,'narrative',self.policy['punctuation']))

    def fixture(self):
        return ({'locale':'zh-CN','bs':[],'pda':[{'id':'sample','source':'Cell','target':'隔离室','text_kind':'objective','terms':['cell']}]},
                {'schema':1,'locale':'zh-CN','entries':[{'id':'cell','source':'Cell','preferred':'隔离室','category':'location','status':'active','evidence':['synthetic']}]})

    def test_glossary_reference_spelling_and_source(self):
        data,glossary=self.fixture()
        self.assertEqual(check_data(data,self.policy,glossary),[])
        for field,value in [('target','病房'),('source','unrelated'),('terms',['missing']),('text_kind','unknown')]:
            changed=copy.deepcopy(data);changed['pda'][0][field]=value
            self.assertTrue(check_data(changed,self.policy,glossary))

    def test_proposed_terms_cannot_be_used_as_approved(self):
        data,glossary=self.fixture();glossary['entries'][0]['status']='proposed'
        self.assertTrue(check_data(data,self.policy,glossary))

    def test_duplicate_glossary_and_locale_mismatch_rejected(self):
        data,glossary=self.fixture();glossary['entries']*=2
        with self.assertRaises(ValueError):check_data(data,self.policy,glossary)
        data,glossary=self.fixture();glossary['locale']='ja-JP'
        with self.assertRaises(ValueError):check_data(data,self.policy,glossary)

    def test_repository_translations(self):
        self.assertEqual(check_locale(ROOT/'locales/zh-CN'),[])


if __name__=='__main__':unittest.main()
