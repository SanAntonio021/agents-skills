"""Reject mismatched CLI document, board and redirected browser identities."""
import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from whiteboard import Runner, VerificationError, validate_document_identity


class DocumentIdentity(unittest.TestCase):
    def request(self, route='wiki/WikiTest'):
        return dict(document_url='https://test.feishu.cn/'+route,whiteboard_token='BoardTest',operations=[])

    def response(self, content=None, token='DocTest'):
        return {'ok':True,'data':{'document':{'document_id':token,'revision_id':8,
            'content':content or '<title id="DocTest">Test</title><whiteboard id="BlockTest" token="BoardTest"></whiteboard>'}}}

    def test_wiki_resolves_docx_and_exact_whiteboard_block(self):
        identity=validate_document_identity(self.request(),self.response())
        self.assertEqual(identity,dict(docx_token='DocTest',whiteboard_token='BoardTest',block_id='BlockTest',revision_id=8))
        self.assertEqual(identity,validate_document_identity(self.request('docx/DocTest'),self.response()))

    def test_wrong_doc_board_block_or_ambiguous_board_rejected(self):
        cases=[(self.request('docx/Wrong'),self.response()),
               (dict(self.request(),docx_token='Wrong'),self.response()),
               (dict(self.request(),block_id='Wrong'),self.response()),
               (self.request(),self.response('<whiteboard id="Other" token="OtherBoard"></whiteboard>')),
               (self.request(),self.response('<whiteboard id="a" token="BoardTest"></whiteboard><whiteboard id="b" token="BoardTest"></whiteboard>')),
               (self.request(),self.response('<whiteboard token="BoardTest"></whiteboard>')),
               (self.request(),self.response('<broken>'))]
        for request,response in cases:
            with self.subTest(request=request,response=response),self.assertRaises(VerificationError):
                validate_document_identity(request,response)

    def runner(self, final_url, final_response=None):
        runner=Runner.__new__(Runner)
        runner.request=self.request('docx/DocTest')
        runner.report={'pages':[],'document_routes':[]}
        runner.responses=[self.response(),final_response or self.response()]
        runner.command=lambda args:runner.responses.pop(0)
        runner.calls=[]
        def call(path,data=None,auth=True):
            runner.calls.append((path,data))
            if path=='/v2/tasks':return {'taskToken':'private','taskId':'task'}
            if path=='/v2/tabs':return {'targetId':'tab'}
            if path.endswith('/eval'):return {'value':{'origin':final_url.split('/wiki')[0].split('/docx')[0], 'href':final_url}}
            return {}
        runner.call=call
        return runner

    def test_docx_redirect_is_fetch_verified_before_editor(self):
        runner=self.runner('https://test.feishu.cn/wiki/WikiTest')
        runner._open_page()
        self.assertEqual(runner.page_document_url,'https://test.feishu.cn/wiki/WikiTest')
        self.assertEqual(len(runner.report['document_routes']),2)
        self.assertEqual(runner.document_identity['docx_token'],'DocTest')

    def test_redirected_origin_path_query_doc_and_board_rejected(self):
        cases=[('https://other.feishu.cn/wiki/WikiTest',None),
               ('https://test.feishu.cn/drive/WikiTest',None),
               ('https://test.feishu.cn/wiki/WikiTest?session=x',None),
               ('https://test.feishu.cn/wiki/WikiTest',self.response(token='Wrong')),
               ('https://test.feishu.cn/wiki/WikiTest',self.response('<whiteboard id="Other" token="OtherBoard"></whiteboard>'))]
        for url,response in cases:
            runner=self.runner(url,response)
            with self.subTest(url=url,response=response),self.assertRaises((VerificationError,ValueError)):
                runner._open_page()
            self.assertNotEqual(runner.report['pages'][0]['open_status'],'ready')

    def test_unresolved_identity_rejects_before_browser_task(self):
        runner=self.runner('https://test.feishu.cn/wiki/WikiTest')
        runner.responses[0]=self.response(token='Wrong')
        with self.assertRaises(VerificationError):runner._open_page()
        self.assertEqual(runner.calls,[])

    def test_independent_text_clear_is_rejected_before_editor(self):
        from whiteboard import validate_local_operation
        node=dict(id='text',kind='text',text='existing',x=0,y=0,width=100,height=20)
        with self.assertRaisesRegex(VerificationError,'Clearing an independent'):
            validate_local_operation([node],dict(kind='text',id='text',text=''))
        validate_local_operation([node],dict(kind='text',id='text',text='new text'))
        validate_local_operation([dict(node,kind='shape')],dict(kind='text',id='text',text=''))

    def test_saved_new_caption_only_accepts_observed_theme_default(self):
        from whiteboard import check_raw_preservation
        from native_nodes import compile_diagram
        before=compile_diagram({'shapes':[dict(id='a',x=0,y=0,width=100,height=60),dict(id='b',x=300,y=0,width=100,height=60)],
                                'connectors':[dict(id='c',start_id='a',end_id='b')]})
        after=copy.deepcopy(before)
        line=after['nodes'][-1]
        line['connector'].update(captions={'data':[dict(text='label\nsecond line',font_size=14,text_color='#1f2329',text_color_type=0,theme_text_color_code=-1)]},
                                 caption_position=.5,caption_position_type=0)
        op=dict(kind='caption',id='c',text='label\nsecond line')
        exceptions=check_raw_preservation(before,after,op)
        self.assertEqual(exceptions[0]['normalization'],'native_default_caption_theme')
        for field,value in [('theme_text_color_code',0),('theme_text_color_code',-1.0),('text_color_type',1),('unknown',False)]:
            invalid=copy.deepcopy(after)
            invalid['nodes'][-1]['connector']['captions']['data'][0][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(VerificationError):
                check_raw_preservation(before,invalid,op)
        unrelated=copy.deepcopy(after);unrelated['nodes'][0]['locked']=True
        with self.assertRaises(VerificationError):check_raw_preservation(before,unrelated,op)


if __name__=='__main__':unittest.main()
