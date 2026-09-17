import base64
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from model import *
from engine import *
import hwpx
from transcription import classify_transcript, register_transcript

class DomainTests(unittest.TestCase):
    def setUp(self):self.d=seed()
    def test_seed_scope_and_original_numbers(self):
        self.assertEqual(value(self.d['kpis'][0]['baseline']),6)
        self.assertEqual(value(self.d['kpis'][0]['target']),10)
        self.assertFalse(kpi_achieved(self.d,self.d['kpis'][0]))
        self.assertEqual(sum(value(a['amount']) for a in self.d['assets']),48000000)
        self.assertFalse(any(x['code'].startswith(('BUDGET_','QUOTE_')) for x in validate(self.d)))
    def test_unknown_numeric_never_becomes_zero(self):
        self.assertEqual(show(self.d,fact(missing='measurement')),'[현장 측정 필요]')
        self.assertEqual(show(self.d,fact(0,'case4','case')),'0')
    def test_number_without_evidence_redacted(self):
        self.d['kpis'][0]['baseline']=fact(937,'','verified','measurement')
        self.assertNotIn('937',json.dumps(compose(self.d,'result')['sections']))
        self.assertTrue(any(x['code']=='EVIDENCE' for x in validate(self.d)))
    def test_source_type_cannot_launder_statement(self):
        f=fact(10,'user-result','verified','measurement')
        self.assertFalse(supported(self.d,f))
        self.assertEqual(show(self.d,f),'[현장 측정 필요]')
    def test_case_data_not_customer_fact(self):
        self.d['mode']='field'
        self.assertEqual(show(self.d,self.d['kpis'][0]['baseline']),'[현장 측정 필요]')
    def test_budget_cash_and_inkind(self):
        self.d['budget']['total']['value']=48000000
        codes={x['code'] for x in validate(self.d)}
        self.assertTrue({'BUDGET_TOTAL','QUOTE_TOTAL'}<=codes)
    def test_relations_and_duplicate_ids(self):
        self.d['assets'][0]['supplier_id']['value']='missing'
        self.assertTrue(any(x['code']=='RELATION' for x in validate(self.d)))
        self.d['assets'].append(deepcopy(self.d['assets'][0]))
        with self.assertRaises(ValueError):validate_shape(self.d)
    def test_invalid_numbers(self):
        for v in [-1,float('nan'),float('inf'),True,'6']:
            self.d['kpis'][0]['baseline']['value']=v
            with self.assertRaises(ValueError):validate_shape(self.d)
    def test_transcript_summary_and_evidence_registration(self):
        text='CNC 장비가 노후되어 가공 중 멈추는 문제가 있습니다. MES를 도입해 생산량 기록을 자동화하고 싶습니다. 목표는 하루 12개입니다.'
        memo='현장 메모: 장비 모델과 목표 생산량은 견적서 및 생산원장으로 재확인 필요'
        updated,session=register_transcript(self.d,text,'2','2026-09-17T01:00:00+00:00',memo)
        validate_shape(updated)
        self.assertEqual(value(updated['implementation']['status']),value(self.d['implementation']['status']))
        self.assertTrue({'problems','assets','datasets','kpis'}<={c for x in classify_transcript(text) for c in x['categories']})
        self.assertIn('[문제]',session['summary']);self.assertIn('[KPI]',session['summary'])
        self.assertEqual(session['memo'],memo)
        evidence=next(e for e in updated['evidence'] if e['id']==session['evidence_id'])
        self.assertEqual(evidence['type'],'statement');self.assertIn('[전사 원문]\n'+text,evidence['excerpt']);self.assertIn('[현장 메모]\n'+memo,evidence['excerpt'])
        self.assertTrue(session['registered_paths'])
        # Spoken numbers remain quoted text; no structured current/target/actual value is inferred.
        for kpi in updated['kpis'][len(self.d['kpis']):]:
            self.assertIsNone(value(kpi['baseline']));self.assertIsNone(value(kpi['target']));self.assertIsNone(value(kpi['actual']))
    def test_run_on_transcript_is_segmented_and_not_repeated(self):
        text=('골프 양말 위주 특화 상품을 제조하고 있으나 봉조 공정을 내부 인력으로 진행하고 있어 '
              '그래서 인건비 부담과 원가 상승으로 경쟁력이 약화되고 있어 연간 매출액은 2억 원 이상이고 총 6명이 근무하고 있어 '
              '공정 자동화를 위해 양말 직조와 봉조를 동시에 수행할 장비 도입을 계획하고 있으며 현재 자동 봉조가 불가능한 장비 20대를 보유하고 있어 '
              '지원사업으로 2대를 우선 교체하고 향후 순차 교체할 계획입니다 하드웨어는 양말 편직기 2대이고 대당 약 2100만 원이며 '
              '소프트웨어는 그리드 프로그램으로 약 600만 원입니다')
        classified=classify_transcript(text);summary=register_transcript(self.d,text,'1')[1]['summary']
        self.assertGreater(len(classified),5)
        self.assertNotIn(text,summary)
        self.assertLess(max(map(len,summary.splitlines())),220)
        self.assertEqual(summary.count('골프 양말'),1)
        self.assertIn('[문제]',summary);self.assertIn('[개선과제]',summary);self.assertIn('[H/W·S/W]',summary)
    def test_transition_rejects_skip_and_future(self):
        for state,day in [('성과달성',date.today().isoformat()),('시범운영',(date.today()+timedelta(days=1)).isoformat())]:
            with self.assertRaises(ValueError):transition(self.d,state,'user-result',day,'상태 확인')
    def test_transition_requires_evidence(self):
        with self.assertRaises(ValueError):transition(self.d,'시범운영','design',date.today().isoformat(),'계획')
        nxt=transition(self.d,'시범운영','user-result',date.today().isoformat(),'사용자 시범운영 확인')
        self.assertEqual(value(nxt['implementation']['status']),'시범운영')
        self.assertEqual(value(self.d['implementation']['status']),'설치')
    def test_achievement_requires_measurement(self):
        self.d['implementation']['status']=fact('성과측정','user-result','user_statement')
        with self.assertRaises(ValueError):transition(self.d,'성과달성','user-result',date.today().isoformat(),'달성')
        self.d['evidence'].append({'id':'m','title':'실제 생산원장','type':'measurement','locator':'검증용 원장','excerpt':'동일 조건 측정'})
        k=self.d['kpis'][0];k['actual']=fact(10,'m','verified')
        k['period']=fact('검증용 측정기간','m','verified');k['owner']=fact('측정담당','m','verified')
        self.assertTrue(kpi_achieved(self.d,k))
        self.assertEqual(value(transition(self.d,'성과달성','m',date.today().isoformat(),'생산원장 대조')['implementation']['status']),'성과달성')
        k['actual']['value']=9;self.assertFalse(kpi_achieved(self.d,k))
    def test_future_submission_not_composed(self):
        self.d['implementation']['submitted_at']=fact('2999-01-01','v3','verified')
        self.d['implementation']['submission']=fact('완료','v3','verified')
        doc=compose(self.d,'visit3')
        self.assertEqual(doc['fields']['implementation.submission'],'[추가 확인 필요]')
    def test_five_docs_same_business_values(self):
        docs=[compose(self.d,k) for k in DOCS]
        for key in ['company.name','assets.0.model','kpis.0.target','budget.total']:
            self.assertEqual(len({x['fields'][key] for x in docs}),1)
        self.assertNotIn('실적 10',docs[0]['sections'][0]['text'])
        result=docs[-1]
        self.assertIn('성과달성 판정은 보류',result['fields']['sections.kpi'])
        for key in ['company','purpose','kpi','assets','data','opinion']:
            self.assertGreaterEqual(len(result['fields']['sections.'+key].splitlines()),3)
    def test_document_version_detection(self):
        issues=validate(self.d,[{'kind':'visit1','project_version':1},{'kind':'result','project_version':2}],2)
        self.assertTrue({'STALE_DOCUMENT','DOCUMENT_VERSION'}<={x['code'] for x in issues})
    def test_document_value_comparison(self):
        a={'kind':'visit2','project_version':1,'source':self.d,'content':compose(self.d,'visit2')}
        b={'kind':'plan','project_version':1,'source':self.d,'content':compose(self.d,'plan')}
        b['content']['fields']['assets.0.model']='다른 모델'
        codes={x['code'] for x in validate(self.d,[a,b],1)}
        self.assertTrue({'DOCUMENT_SOURCE_MISMATCH','DOCUMENT_FIELD_MISMATCH'}<=codes)

class HwpxTests(unittest.TestCase):
    def test_all_official_templates_preserve_package_and_structure(self):
        d=seed()
        for kind in DOCS:
            raw=(app.ROOT/'templates'/f'{kind}.hwpx').read_bytes()
            mapping=json.loads((app.ROOT/'templates'/f'{kind}.mapping.json').read_text('utf-8'))
            result=hwpx.fill(raw,hashlib.sha256(raw).hexdigest(),mapping,compose(d,kind)['fields'])
            before=zipfile.ZipFile(io.BytesIO(raw));after=zipfile.ZipFile(io.BytesIO(result))
            self.assertEqual(before.namelist(),after.namelist())
            for n in before.namelist():
                if not n.startswith('Contents/section'):self.assertEqual(before.read(n),after.read(n),n)
                else:
                    # Text nodes may be added to formerly empty runs; table/run/style topology stays.
                    signature=lambda r:[(x.tag,dict(x.attrib)) for x in ET.fromstring(r).iter() if not x.tag.endswith('}t')]
                    self.assertEqual(signature(before.read(n)),signature(after.read(n)))
                    self.assertIn('(주)블루스카이',after.read(n).decode())
            # Separate sample pages remain untouched in visits.
            if kind.startswith('visit'):self.assertIn('정밀테크(가칭)',after.read('Contents/section0.xml').decode())
    def test_xml_escaping_and_original_hash(self):
        raw=(app.ROOT/'templates'/'result.hwpx').read_bytes();h=hashlib.sha256(raw).hexdigest()
        n=hwpx.inspect(raw)['nodes'][8];mp=[dict(part=n['part'],index=8,expected='',field='x')]
        result=hwpx.fill(raw,h,mp,{'x':'가&나 <확인> "인용"'})
        z=zipfile.ZipFile(io.BytesIO(result));root=ET.fromstring(z.read(n['part']))
        self.assertIn('가&나 <확인> "인용"',''.join(root.itertext()))
        with self.assertRaises(ValueError):hwpx.fill(raw,'wrong',mp,{'x':'a'})
        with self.assertRaises(ValueError):hwpx.fill(raw,h,mp+mp,{'x':'a'})
        mp[0]['expected']='changed'
        with self.assertRaises(ValueError):hwpx.fill(raw,h,mp,{'x':'a'})
    def test_invalid_archive(self):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:z.writestr('../escape','bad')
        with self.assertRaises(ValueError):hwpx.inspect(out.getvalue())

class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();app.DATA=Path(cls.temp.name);app.DB=app.DATA/'test.sqlite3';app.initialize()
        cls.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);cls.server.allow_lan=False;cls.server.access_token='';cls.server.trusted_hosts=set();cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start();cls.base='http://127.0.0.1:'+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.temp.cleanup()
    def request(self,path,method='GET',data=None,headers=None):
        h=headers or {};h['Content-Type']='application/json'
        req=Request(self.base+path,method=method,headers=h,data=None if data is None else json.dumps(data).encode())
        try:
            with urlopen(req) as r:return r.status,r.read()
        except HTTPError as e:return e.code,e.read()
    def test_crud_generation_backup_and_restore(self):
        status,body=self.request('/api/projects','POST',{'name':'통합시험 기업'});self.assertEqual(status,200);p=json.loads(body);pid=p['id']
        d=p['data'];d['company']['industry']=fact('시험 제조','manual','user_statement')
        status,body=self.request('/api/projects/'+pid,'PUT',{'data':d,'expected_version':1,'reason':'통합시험'});self.assertEqual(status,200)
        self.assertEqual(json.loads(self.request('/api/projects/'+pid)[1])['version'],2)
        self.assertEqual(self.request('/api/projects/'+pid,'PUT',{'data':d,'expected_version':1,'reason':'충돌시험'})[0],409)
        self.assertEqual(self.request('/api/projects/'+pid+'/generate','POST',{'kind':'result'})[0],409)
        status,body=self.request('/api/projects/'+pid+'/generate','POST',{'kind':'all'});self.assertEqual(status,200);self.assertEqual(len(json.loads(body)),5)
        backup=json.loads(self.request('/api/projects/'+pid+'/backup')[1]);self.assertEqual(len(backup['revisions']),2)
        status,restored=self.request('/api/projects/import','POST',{'backup':backup});self.assertEqual(status,200)
        new=json.loads(restored);self.assertNotEqual(new['id'],pid);self.assertEqual(new['data'],d)
        self.assertEqual(len(json.loads(self.request('/api/projects/'+new['id']+'/documents')[1])),5)
        self.assertTrue(app.DB.exists())
    def test_hwpx_endpoint(self):
        status,body=self.request('/api/projects/case4/generate','POST',{'kind':'all'});self.assertEqual(status,200)
        for doc in json.loads(body):
            status,raw=self.request('/api/documents/'+doc['id']+'/hwpx','POST',{'template_id':'official-'+doc['kind']})
            self.assertEqual(status,200);self.assertTrue(zipfile.is_zipfile(io.BytesIO(raw)))
            self.assertIn('(주)블루스카이',zipfile.ZipFile(io.BytesIO(raw)).read('Contents/section0.xml').decode())
    def test_hwpx_rejects_wrong_official_form(self):
        status,body=self.request('/api/projects/case4/generate','POST',{'kind':'all'})
        doc=json.loads(body)[0]
        status,body=self.request('/api/documents/'+doc['id']+'/hwpx','POST',{'template_id':'official-result'})
        self.assertEqual(status,422)
        self.assertIn('종류가 다릅니다',json.loads(body)['error'])
    def test_live_transcription_registers_new_version(self):
        p=json.loads(self.request('/api/projects/case4')[1])
        payload={'text':'수기 작업일보 때문에 생산실적 집계가 늦습니다. MES 도입으로 데이터를 자동 수집해야 합니다.','memo':'현장에서 설비별 기록지를 추가 확인하기로 함','visit_round':'1','expected_version':p['version']}
        status,body=self.request('/api/projects/case4/transcriptions','POST',payload)
        self.assertEqual(status,200);result=json.loads(body)
        self.assertEqual(result['project']['version'],p['version']+1)
        self.assertGreater(len(result['transcription']['registered_paths']),1)
        rows=json.loads(self.request('/api/projects/case4/transcriptions')[1])
        self.assertEqual(rows[0]['project_version'],result['project']['version'])
        self.assertIn('[문제]',rows[0]['summary'])
        self.assertEqual(rows[0]['memo'],payload['memo'])
        status,body=self.request(f'/api/projects/case4/transcriptions/{rows[0]["id"]}/reprocess','POST',{'expected_version':result['project']['version']})
        self.assertEqual(status,200);reprocessed=json.loads(body)
        self.assertEqual(reprocessed['project']['version'],result['project']['version']+1)
        rows=json.loads(self.request('/api/projects/case4/transcriptions')[1])
        self.assertEqual(rows[0]['project_version'],reprocessed['project']['version'])
        edit={'expected_version':reprocessed['project']['version'],'transcript':'수정한 전사 원문입니다. 생산실적 수집 절차를 확인했습니다.','memo':'수정한 현장 메모','summary':'[검토 요약]\n사용자가 전사와 메모를 함께 검토한 요약'}
        status,body=self.request(f'/api/projects/case4/transcriptions/{rows[0]["id"]}','PUT',edit)
        self.assertEqual(status,200);edited=json.loads(body)
        self.assertEqual(edited['project']['version'],reprocessed['project']['version']+1)
        rows=json.loads(self.request('/api/projects/case4/transcriptions')[1])
        self.assertEqual(rows[0]['transcript'],edit['transcript']);self.assertEqual(rows[0]['memo'],edit['memo']);self.assertEqual(rows[0]['summary'],edit['summary'])
        stale={'text':'다시 등록','visit_round':'1','expected_version':p['version']}
        self.assertEqual(self.request('/api/projects/case4/transcriptions','POST',stale)[0],409)
    def test_mobile_token_sets_cookie_and_protects_access(self):
        self.server.access_token='mobile-test-token';self.server.trust_loopback=False
        try:
            self.assertEqual(self.request('/api/schema')[0],403)
            with urlopen(Request(self.base+'/?token=mobile-test-token')) as response:
                self.assertEqual(response.status,200);cookie=response.headers['Set-Cookie'].split(';',1)[0]
            with urlopen(Request(self.base+'/api/schema',headers={'Cookie':cookie})) as response:
                self.assertEqual(response.status,200);self.assertIn('groups',json.loads(response.read()))
        finally:self.server.access_token='';self.server.trust_loopback=True
    def test_public_deployment_requires_basic_auth(self):
        public_host='smart-coordinator.up.railway.app';self.server.trusted_hosts={public_host}
        auth='Basic '+base64.b64encode('field-user:correct-secret'.encode()).decode()
        try:
            with patch.dict(os.environ,{'COORDINATOR_USERNAME':'field-user','COORDINATOR_PASSWORD':'correct-secret','COORDINATOR_REQUIRE_AUTH':'1'}):
                headers={'Host':public_host,'Origin':'https://'+public_host}
                status,body=self.request('/api/schema',headers=headers.copy());self.assertEqual(status,401);self.assertIn('로그인',json.loads(body)['error'])
                headers['Authorization']=auth
                self.assertEqual(self.request('/api/schema',headers=headers)[0],200)
            with patch.dict(os.environ,{'COORDINATOR_PASSWORD':'','COORDINATOR_REQUIRE_AUTH':'1'}):
                self.assertEqual(self.request('/api/schema',headers={'Host':public_host,'Origin':'https://'+public_host})[0],503)
            self.assertEqual(self.request('/health')[0],200)
        finally:self.server.trusted_hosts=set()
    def test_realtime_capability_keeps_api_key_on_server(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':''}):
            status,body=self.request('/api/realtime/capabilities')
            self.assertEqual(status,200)
            capability=json.loads(body)
            self.assertFalse(capability['openai_realtime'])
            self.assertNotIn('api_key',capability)
            status,body=self.request('/api/realtime/session','POST',{'sdp':'v=0\r\n'})
            self.assertEqual(status,503)
            self.assertIn('OPENAI_API_KEY',json.loads(body)['error'])
    def test_realtime_session_proxies_sdp_with_server_key(self):
        captured={}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*_):return False
            def read(self,_):return b'v=0\r\no=answer\r\n'
        def fake_open(req,timeout):
            captured['authorization']=req.get_header('Authorization')
            captured['body']=req.data.decode('utf-8')
            captured['timeout']=timeout
            return Response()
        with patch.dict(os.environ,{'OPENAI_API_KEY':'server-secret'}),patch.object(app,'urlopen',side_effect=fake_open):
            result=app.realtime_session('v=0\r\no=offer\r\n')
        self.assertEqual(result['model'],'gpt-live-transcribe')
        self.assertEqual(captured['authorization'],'Bearer server-secret')
        self.assertIn('"languages": ["ko"]'.replace(' ',''),captured['body'].replace(' ',''))
        self.assertNotIn('server-secret',captured['body'])
    def test_direct_status_edit_blocked(self):
        p=json.loads(self.request('/api/projects/case4')[1]);p['data']['implementation']['status']['value']='성과달성'
        self.assertEqual(self.request('/api/projects/case4','PUT',{'data':p['data'],'expected_version':p['version'],'reason':'직접상태변경'})[0],409)
    def test_malformed_and_origin(self):
        self.assertEqual(self.request('/api/projects','POST',{}, {'Origin':'https://untrusted.example'})[0],403)
        self.assertEqual(self.request('/api/schema','GET',headers={'Host':'coordinator.example.ts.net','Origin':'https://coordinator.example.ts.net'})[0],200)
        self.assertEqual(self.request('/api/projects/case4','PUT',{'data':{}})[0],422)
        self.assertEqual(self.request('/../schema.sql')[0],404)
    def test_app_resources_available(self):
        import re
        status,body=self.request('/')
        self.assertEqual(status,200)
        for path in re.findall(r'(?:src|href)="(/[^"]+)"',body.decode()):
            self.assertEqual(self.request(path)[0],200,path)
        self.assertEqual(self.request('/service-worker.js')[0],200)
        manifest=json.loads(self.request('/manifest.webmanifest')[1]);self.assertEqual(manifest['display'],'standalone')

if __name__=='__main__':unittest.main(verbosity=2)
