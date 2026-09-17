"""Local single-user web application. Run: python app.py"""
import argparse
import base64
from contextlib import contextmanager
from http.cookies import SimpleCookie
from datetime import datetime, timezone
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import mimetypes
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import uuid
import zipfile
import xml.etree.ElementTree as ET
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import parse_qs, urlparse

from model import *
from engine import compose, validate, transition, prompt_package
import hwpx
from transcription import register_transcript

ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('COORDINATOR_DATA',str(ROOT/'data'))).resolve()
DB=DATA/'coordinator.sqlite3'
ACCESS_COOKIE='coordinator_access'

def now():return datetime.now(timezone.utc).isoformat(timespec='microseconds')
def dumps(x):return json.dumps(x,ensure_ascii=False,allow_nan=False)

def is_loopback_host(host):
    if host in ('localhost','127.0.0.1','::1'):return True
    try:return ipaddress.ip_address(host).is_loopback
    except ValueError:return False

def lan_addresses():
    addresses=set()
    try:
        for item in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET):
            ip=item[4][0]
            if ipaddress.ip_address(ip).is_private and not ipaddress.ip_address(ip).is_loopback:addresses.add(ip)
    except OSError:pass
    def priority(ip):
        address=ipaddress.ip_address(ip)
        if address in ipaddress.ip_network('192.168.0.0/16'):return 0
        if address in ipaddress.ip_network('10.0.0.0/8'):return 1
        if address in ipaddress.ip_network('172.16.0.0/12'):return 2
        return 3
    return sorted(addresses,key=lambda ip:(priority(ip),ip))
def uid():return uuid.uuid4().hex

@contextmanager
def database():
    con=sqlite3.connect(DB,timeout=10);con.row_factory=sqlite3.Row;con.execute('PRAGMA foreign_keys=ON')
    try:
        with con:yield con
    finally:con.close()

def project(con,pid):
    r=con.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone()
    if not r:raise LookupError('기업을 찾을 수 없습니다.')
    return {'id':r['id'],'version':r['version'],'data':json.loads(r['data_json']),'created_at':r['created_at'],'updated_at':r['updated_at']}

def create_project(con,d,reason='신규 기업 등록',pid=None):
    validate_shape(d);pid=pid or uid();t=now();raw=dumps(d)
    con.execute('INSERT INTO projects VALUES(?,?,?,?,?,?)',(pid,value(d['company']['name']) or '미정',1,raw,t,t))
    con.execute('INSERT INTO revisions VALUES(?,?,?,?,?)',(pid,1,raw,reason,t))
    return project(con,pid)

class Conflict(Exception):pass
class RealtimeUnavailable(Exception):pass
class RealtimeServiceError(Exception):pass
class AuthenticationRequired(Exception):pass

def realtime_capabilities():
    return {
        'openai_realtime':bool(os.environ.get('OPENAI_API_KEY','').strip()),
        'model':'gpt-live-transcribe',
        'audio_stored':False,
    }

def realtime_session(sdp):
    """Exchange a browser WebRTC offer for an OpenAI Realtime answer.

    The standard API key remains on this local server. The browser receives only
    the SDP answer and then sends microphone media over the WebRTC connection.
    """
    api_key=os.environ.get('OPENAI_API_KEY','').strip()
    if not api_key:raise RealtimeUnavailable('OPENAI_API_KEY가 설정되지 않았습니다. 수동 전사문 입력은 계속 사용할 수 있습니다.')
    if not isinstance(sdp,str) or not sdp.startswith('v=0') or len(sdp)>1024*1024:
        raise ValueError('올바른 WebRTC SDP offer가 필요합니다.')
    session={
        'type':'transcription',
        'audio':{'input':{
            'transcription':{
                'model':'gpt-live-transcribe',
                'prompt':'한국어 스마트제조 현장 인터뷰. 제조공정, 문제, 원인, 개선과제, H/W, S/W, 제조데이터, KPI, 사업비, 공급기업과 구축상태를 정확히 전사한다.',
                'languages':['ko'],
                'delay':'low',
            },
            'turn_detection':{'type':'server_vad','prefix_padding_ms':300,'silence_duration_ms':700},
        }},
    }
    boundary='----CoordinatorMVP'+uuid.uuid4().hex
    chunks=[]
    for name,value_ in (('sdp',sdp),('session',dumps(session))):
        chunks.extend([
            f'--{boundary}\r\n'.encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value_.encode('utf-8'),b'\r\n',
        ])
    chunks.append(f'--{boundary}--\r\n'.encode())
    req=Request('https://api.openai.com/v1/realtime/calls',data=b''.join(chunks),method='POST',headers={
        'Authorization':'Bearer '+api_key,
        'Content-Type':'multipart/form-data; boundary='+boundary,
        'OpenAI-Safety-Identifier':'coordinator-mvp-local-user',
    })
    try:
        with urlopen(req,timeout=30) as response:
            answer=response.read(2*1024*1024).decode('utf-8')
    except HTTPError as e:
        detail=e.read(3000).decode('utf-8','replace')
        try:detail=json.loads(detail).get('error',{}).get('message',detail)
        except (ValueError,AttributeError):pass
        raise RealtimeServiceError('OpenAI 실시간 전사 연결 실패: '+str(detail)[:500]) from e
    except (URLError,TimeoutError) as e:
        raise RealtimeServiceError('OpenAI 실시간 전사 서버에 연결할 수 없습니다.') from e
    if not answer.startswith('v=0'):raise RealtimeServiceError('OpenAI에서 올바른 WebRTC 응답을 받지 못했습니다.')
    return {'sdp':answer,'model':'gpt-live-transcribe'}

def save_project(con,pid,d,expected,reason,allow_transition=False):
    validate_shape(d)
    if not isinstance(reason,str) or not reason.strip():raise ValueError('변경사유를 입력하세요.')
    con.execute('BEGIN IMMEDIATE')
    old=project(con,pid)
    if old['version']!=expected:raise Conflict('다른 화면에서 저장되었습니다. 새로고침 후 다시 수정하세요.')
    if not allow_transition and d['implementation']['status']!=old['data']['implementation']['status']:raise Conflict('현재 구축상태는 상태변경 화면에서 근거와 함께 변경하세요.')
    ver=expected+1;raw=dumps(d);t=now()
    con.execute('UPDATE projects SET name=?,version=?,data_json=?,updated_at=? WHERE id=?',(value(d['company']['name']) or '미정',ver,raw,t,pid))
    con.execute('INSERT INTO revisions VALUES(?,?,?,?,?)',(pid,ver,raw,reason,t))
    con.execute('INSERT INTO audit_log(project_id,action,detail_json,created_at) VALUES(?,?,?,?)',(pid,'transition' if allow_transition else 'save',dumps({'from_version':expected,'to_version':ver,'reason':reason}),t))
    return project(con,pid)

def documents(con,pid):
    return [dict(r) for r in con.execute('SELECT id,kind,project_version,created_at FROM documents WHERE project_id=? ORDER BY created_at,id',(pid,))]

def transcriptions(con,pid):
    rows=[]
    for r in con.execute('SELECT * FROM transcriptions WHERE project_id=? ORDER BY created_at DESC,id DESC',(pid,)):
        x=dict(r);x['categories']=json.loads(x.pop('categories_json'));x['registered_paths']=json.loads(x.pop('registered_json'));rows.append(x)
    return rows

def _rebuild_transcription(con,pid,tid,expected,transcript=None,memo=None,summary_override=None,
        reason='실시간 전사 요약·분류 규칙 교정',action='transcription_reprocess'):
    pr=project(con,pid)
    if pr['version']!=expected:raise Conflict('원장 버전이 변경되었습니다. 새로고침 후 다시 시도하세요.')
    row=con.execute('SELECT * FROM transcriptions WHERE id=? AND project_id=?',(tid,pid)).fetchone()
    if not row:raise LookupError('전사 기록을 찾을 수 없습니다.')
    if row['project_version']!=pr['version']:
        raise Conflict('가장 최근 원장 변경이 이 전사 등록인 경우에만 자동 교정할 수 있습니다.')
    registered_version=None
    for audit in con.execute("SELECT detail_json FROM audit_log WHERE project_id=? AND action='transcription_register' ORDER BY id",(pid,)):
        detail=json.loads(audit['detail_json'])
        if detail.get('transcription_id')==tid:registered_version=detail.get('project_version');break
    base_version=(registered_version or row['project_version'])-1
    previous=con.execute('SELECT data_json FROM revisions WHERE project_id=? AND version=?',(pid,base_version)).fetchone()
    if not previous:raise Conflict('전사 등록 전 원장 버전을 찾을 수 없습니다.')
    transcript=row['transcript'] if transcript is None else transcript
    memo=row['memo'] if memo is None else memo
    if not isinstance(summary_override,(str,type(None))) or (isinstance(summary_override,str) and (not summary_override.strip() or len(summary_override)>5000)):
        raise ValueError('요약은 1자 이상 5,000자 이하로 입력하세요.')
    base=json.loads(previous['data_json'])
    data,session=register_transcript(base,transcript,row['visit_round'],row['created_at'],memo)
    if summary_override is not None:
        session['summary']=summary_override.strip()
        visit=next((v for v in data['visits'] if value(v['round'])==row['visit_round']),None)
        observation_path=f'visits.{visit["id"]}.observations' if visit else ''
        if visit and observation_path in session['registered_paths']:
            visit['observations']=fact('검토된 전사·메모 요약\n'+session['summary'],session['evidence_id'],'analysis')
    saved=save_project(con,pid,data,pr['version'],reason)
    updated=now()
    con.execute('UPDATE transcriptions SET project_version=?,transcript=?,memo=?,summary=?,categories_json=?,registered_json=?,updated_at=? WHERE id=?',
        (saved['version'],session['transcript'],session['memo'],session['summary'],dumps(session['categories']),dumps(session['registered_paths']),updated,tid))
    con.execute('INSERT INTO audit_log(project_id,action,detail_json,created_at) VALUES(?,?,?,?)',
        (pid,action,dumps({'transcription_id':tid,'from_version':pr['version'],'to_version':saved['version'],
            'evidence_id':session['evidence_id'],'registered_paths':session['registered_paths']}),now()))
    return {'project':saved,'transcription':{'id':tid,'project_version':saved['version'],'updated_at':updated,**session}}

def reprocess_transcription(con,pid,tid,expected):
    return _rebuild_transcription(con,pid,tid,expected)

def edit_transcription(con,pid,tid,expected,transcript,memo,summary):
    return _rebuild_transcription(con,pid,tid,expected,transcript,memo,summary,
        '전사 원문·현장 메모·요약 수정 및 관련 항목 재분류','transcription_edit')

def document(con,did):
    r=con.execute('SELECT * FROM documents WHERE id=?',(did,)).fetchone()
    if not r:raise LookupError('문서를 찾을 수 없습니다.')
    return {'id':r['id'],'project_id':r['project_id'],'project_version':r['project_version'],'kind':r['kind'],'created_at':r['created_at'],'content':json.loads(r['content_json']),'source':json.loads(r['source_json'])}

def generate(con,pid,kind):
    con.execute('BEGIN IMMEDIATE');p=project(con,pid);d=p['data'];existing=documents(con,pid)
    kinds=list(DOCS) if kind=='all' else [kind]
    if kind not in ('all',*DOCS):raise ValueError('알 수 없는 문서유형')
    if kind!='all':
        previous=list(DOCS)[:list(DOCS).index(kind)]
        if any(k not in {x['kind'] for x in existing if x['project_version']==p['version']} for k in previous):raise Conflict('동일 원장 버전의 앞 단계 문서를 먼저 생성하거나 5종 전체 생성을 사용하세요.')
    results=[]
    for k in kinds:
        content=compose(d,k);did=uid()
        content['validation']=validate(d)
        con.execute('INSERT INTO documents VALUES(?,?,?,?,?,?,?)',(did,pid,p['version'],k,dumps(content),dumps(d),now()))
        results.append(document(con,did))
    return results

def template(con,tid):
    r=con.execute('SELECT * FROM templates WHERE id=?',(tid,)).fetchone()
    if not r:raise LookupError('양식을 찾을 수 없습니다.')
    row=dict(r);row['mapping']=json.loads(row.pop('mapping_json'))
    raw=(DATA/'templates'/row['file_name']).read_bytes()
    return row,raw

def register_template(con,name,raw,mapping=None,tid=None):
    inspected=hwpx.inspect(raw);tid=tid or uid();fname=tid+'.hwpx'
    (DATA/'templates'/fname).write_bytes(raw)
    con.execute('INSERT INTO templates VALUES(?,?,?,?,?,?)',(tid,name,inspected['sha256'],fname,dumps(mapping or []),now()))
    return {'id':tid,'name':name,'sha256':inspected['sha256'],'mapping':mapping or [],**inspected}

def initialize():
    DATA.mkdir(parents=True,exist_ok=True);(DATA/'templates').mkdir(exist_ok=True)
    with database() as con:
        con.executescript((ROOT/'schema.sql').read_text('utf-8'))
        columns={r['name'] for r in con.execute('PRAGMA table_info(transcriptions)')}
        if 'memo' not in columns:con.execute("ALTER TABLE transcriptions ADD COLUMN memo TEXT NOT NULL DEFAULT ''")
        if 'updated_at' not in columns:con.execute("ALTER TABLE transcriptions ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
        con.execute("UPDATE transcriptions SET updated_at=created_at WHERE updated_at='' OR updated_at IS NULL")
        if not con.execute('SELECT 1 FROM projects LIMIT 1').fetchone():create_project(con,seed(),'CASE 4 근거자료 기반 초기 데이터','case4')
        for kind,title in DOCS.items():
            f=ROOT/'templates'/(kind+'.hwpx')
            if f.exists() and not con.execute('SELECT 1 FROM templates WHERE id=?',('official-'+kind,)).fetchone():
                mp=ROOT/'templates'/(kind+'.mapping.json')
                register_template(con,title+' 공식 원본',f.read_bytes(),json.loads(mp.read_text('utf-8')) if mp.exists() else [],'official-'+kind)
            elif f.exists():
                r=con.execute('SELECT mapping_json FROM templates WHERE id=?',('official-'+kind,)).fetchone()
                mp=ROOT/'templates'/(kind+'.mapping.json')
                if r and r['mapping_json']=='[]' and mp.exists():con.execute('UPDATE templates SET mapping_json=? WHERE id=?',(mp.read_text('utf-8'),'official-'+kind))

def text_document(doc):
    c=doc['content']
    return f'{c["title"]} / 초안 / 원장 v{doc["project_version"]}\n'+('교육 CASE 4 — 실제 고객사 자료와 구분\n' if c['mode']=='training' else '')+'\n\n'.join(s['title']+'\n'+s['text'] for s in c['sections'])

class Handler(BaseHTTPRequestHandler):
    server_version='CoordinatorMVP/1.0'
    def log_message(self,fmt,*args):pass
    def send(self,obj,status=200,ctype='application/json; charset=utf-8',filename=None):
        data=obj if isinstance(obj,bytes) else dumps(obj).encode('utf-8')
        self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(data)))
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' https://api.openai.com wss://api.openai.com; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if getattr(self,'set_access_cookie',False):
            self.send_header('Set-Cookie',f'{ACCESS_COOKIE}={self.server.access_token}; Path=/; HttpOnly; SameSite=Strict')
        if getattr(self,'auth_challenge',False):self.send_header('WWW-Authenticate','Basic realm="Smart Coordinator", charset="UTF-8"')
        if filename:self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
        self.end_headers();self.wfile.write(data)
    def body(self):
        n=int(self.headers.get('Content-Length','0'))
        if not 0<n<42*1024*1024:raise ValueError('요청 크기가 올바르지 않습니다.')
        if self.headers.get_content_type()!='application/json':raise ValueError('JSON 요청이 필요합니다.')
        return json.loads(self.rfile.read(n),parse_constant=lambda _: (_ for _ in ()).throw(ValueError('유한한 숫자가 필요합니다.')))
    def check_origin(self):
        host=self.headers.get('Host','')
        try:
            parsed_host=urlparse('//'+host);hostname=parsed_host.hostname;port=parsed_host.port
        except ValueError:raise PermissionError('접속 주소가 올바르지 않습니다.')
        if not hostname:raise PermissionError('접속 주소가 올바르지 않습니다.')
        trusted_https_proxy=is_loopback_host(self.client_address[0]) and hostname.lower().endswith('.ts.net')
        trusted_public=hostname.lower() in getattr(self.server,'trusted_hosts',set())
        effective_port=port or (443 if trusted_https_proxy or trusted_public else None)
        if not (trusted_https_proxy or trusted_public) and effective_port!=self.server.server_port:raise PermissionError('접속 주소가 올바르지 않습니다.')
        self.public_request=trusted_public
        if getattr(self.server,'allow_lan',False):
            allowed_name=hostname.lower()==socket.gethostname().lower()
            try:allowed_ip=ipaddress.ip_address(hostname).is_private or ipaddress.ip_address(hostname).is_loopback
            except ValueError:allowed_ip=False
            if not (allowed_name or allowed_ip or trusted_https_proxy or trusted_public):raise PermissionError('같은 로컬 네트워크 주소로 접속하세요.')
        elif not (is_loopback_host(hostname) or trusted_https_proxy or trusted_public):raise PermissionError('로컬 주소로 접속하세요.')
        origin=self.headers.get('Origin')
        if origin:
            parsed_origin=urlparse(origin)
            try:origin_port=parsed_origin.port or (443 if parsed_origin.scheme=='https' else 80)
            except ValueError:raise PermissionError('다른 출처의 요청은 허용하지 않습니다.')
            if parsed_origin.scheme not in ('http','https') or parsed_origin.hostname!=hostname or origin_port!=effective_port:
                raise PermissionError('다른 출처의 요청은 허용하지 않습니다.')
    def check_password(self):
        self.auth_challenge=False
        password=os.environ.get('COORDINATOR_PASSWORD','')
        required=os.environ.get('COORDINATOR_REQUIRE_AUTH','').lower() in ('1','true','yes') or getattr(self,'public_request',False)
        if not password:
            if required:raise RealtimeUnavailable('배포용 COORDINATOR_PASSWORD 환경변수를 먼저 설정하세요.')
            return
        username=os.environ.get('COORDINATOR_USERNAME','coordinator')
        supplied_user=supplied_password=''
        header=self.headers.get('Authorization','')
        if header.startswith('Basic '):
            try:supplied_user,supplied_password=base64.b64decode(header[6:],validate=True).decode('utf-8').split(':',1)
            except (ValueError,UnicodeDecodeError):pass
        if not (hmac.compare_digest(supplied_user,username) and hmac.compare_digest(supplied_password,password)):
            self.auth_challenge=True;raise AuthenticationRequired('로그인이 필요합니다.')
    def check_access(self):
        token=getattr(self.server,'access_token','')
        self.set_access_cookie=False
        if not token:return
        if getattr(self.server,'trust_loopback',True) and is_loopback_host(self.client_address[0]):return
        supplied=parse_qs(urlparse(self.path).query).get('token',[''])[0]
        cookie=SimpleCookie()
        try:cookie.load(self.headers.get('Cookie',''))
        except Exception:pass
        cookie_token=cookie[ACCESS_COOKIE].value if ACCESS_COOKIE in cookie else ''
        if supplied and hmac.compare_digest(supplied,token):self.set_access_cookie=True;return
        if cookie_token and hmac.compare_digest(cookie_token,token):return
        raise PermissionError('모바일 접속 인증이 필요합니다. 실행 창에 표시된 전체 주소를 다시 여세요.')
    def do_GET(self):self.handle_request('GET')
    def do_POST(self):self.handle_request('POST')
    def do_PUT(self):self.handle_request('PUT')
    def handle_request(self,method):
        try:
            path=urlparse(self.path).path
            if path=='/health' and method=='GET':return self.send({'ok':True})
            self.check_origin();self.check_access();self.check_password();parts=path.strip('/').split('/')
            if not path.startswith('/api/'):
                if method!='GET':raise LookupError('없는 경로')
                allowed={'/':'index.html','/app.js':'app.js','/styles.css':'styles.css','/usability.css':'usability.css','/favicon.svg':'favicon.svg','/manifest.webmanifest':'manifest.webmanifest','/service-worker.js':'service-worker.js'}
                if path not in allowed:raise LookupError('없는 경로')
                f=ROOT/'static'/allowed[path]
                return self.send(f.read_bytes(),ctype=(mimetypes.guess_type(f.name)[0] or 'text/plain')+'; charset=utf-8')
            payload=self.body() if method in ('POST','PUT') else {}
            with database() as con:
                result=self.route(con,method,parts,payload)
            if isinstance(result,tuple):return self.send(*result)
            return self.send(result)
        except Conflict as e:self.send({'error':str(e)},409)
        except KeyError as e:self.send({'error':'필수 입력이 없습니다: '+str(e)},422)
        except LookupError as e:self.send({'error':str(e)},404)
        except PermissionError as e:self.send({'error':str(e)},403)
        except AuthenticationRequired as e:self.send({'error':str(e)},401)
        except RealtimeUnavailable as e:self.send({'error':str(e)},503)
        except RealtimeServiceError as e:self.send({'error':str(e)},502)
        except (ValueError,KeyError,TypeError,zipfile.BadZipFile,ET.ParseError) as e:self.send({'error':str(e) or '입력 또는 양식 오류'},422)
        except Exception as e:
            print(type(e).__name__,str(e),flush=True);self.send({'error':'요청 처리 중 오류가 발생했습니다. 저장상태를 확인하세요.'},500)
    def route(self,con,method,p,b):
        if p==['api','schema'] and method=='GET':return {'groups':GROUPS,'kinds':KINDS,'states':STATES,'documents':DOCS,'missing':MISSING}
        if p==['api','realtime','capabilities'] and method=='GET':return realtime_capabilities()
        if p==['api','realtime','session'] and method=='POST':return realtime_session(b.get('sdp'))
        if p==['api','projects']:
            if method=='GET':return [dict(r) for r in con.execute('SELECT id,name,version,updated_at FROM projects ORDER BY created_at')]
            if method=='POST':return create_project(con,blank_project(b.get('name','새 기업')))
        if p==['api','projects','import'] and method=='POST':
            src=b['backup'];d=src['project']['data'];validate_shape(d)
            # Restore into a new project without overwriting the original.
            revisions=src.get('revisions',[]);docs=src.get('documents',[]);transcript_rows=src.get('transcriptions',[])
            if len(revisions)>10000 or len(docs)>10000 or len(transcript_rows)>10000:raise ValueError('백업 크기 제한 초과')
            if not revisions:return create_project(con,d,'백업에서 새 기업 복원')
            versions=[r['version'] for r in revisions]
            if sorted(versions)!=list(range(1,len(versions)+1)) or src['project']['version']!=max(versions):raise ValueError('백업 버전 구조 오류')
            for r in revisions:validate_shape(r['data'])
            if revisions[-1]['data']!=d:raise ValueError('백업 원장과 마지막 이력이 다릅니다.')
            pid=uid();t=now();con.execute('INSERT INTO projects VALUES(?,?,?,?,?,?)',(pid,value(d['company']['name']) or '복원 기업',max(versions),dumps(d),t,t))
            for r in revisions:con.execute('INSERT INTO revisions VALUES(?,?,?,?,?)',(pid,r['version'],dumps(r['data']),r['reason'],r['created_at']))
            for x in docs:
                if x['kind'] not in DOCS or x['project_version'] not in versions:raise ValueError('백업 문서 참조 오류')
                source=next(r['data'] for r in revisions if r['version']==x['project_version'])
                # Re-compose to avoid importing arbitrary purported generated facts.
                con.execute('INSERT INTO documents VALUES(?,?,?,?,?,?,?)',(uid(),pid,x['project_version'],x['kind'],dumps(compose(source,x['kind'])),dumps(source),x['created_at']))
            for x in transcript_rows:
                if x.get('project_version') not in versions or str(x.get('visit_round')) not in ('1','2','3'):raise ValueError('백업 전사기록 참조 오류')
                transcript=x.get('transcript','');memo=x.get('memo','');summary=x.get('summary','')
                if not isinstance(transcript,str) or not isinstance(memo,str) or not isinstance(summary,str) or len(transcript)>20000 or len(memo)>5000 or len(summary)>5000:raise ValueError('백업 전사기록 형식 오류')
                con.execute('INSERT INTO transcriptions(id,project_id,project_version,visit_round,transcript,memo,summary,categories_json,registered_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (uid(),pid,x['project_version'],str(x['visit_round']),transcript,memo,summary,dumps(x.get('categories',[])),dumps(x.get('registered_paths',[])),x['created_at'],x.get('updated_at',x['created_at'])))
            return project(con,pid)
        if len(p)>=3 and p[1]=='projects':
            pid=p[2]
            if len(p)==3:
                if method=='GET':return project(con,pid)
                if method=='PUT':return save_project(con,pid,b['data'],b['expected_version'],b['reason'])
            if len(p)==6 and p[3]=='transcriptions' and p[5]=='reprocess' and method=='POST':
                return reprocess_transcription(con,pid,p[4],b.get('expected_version'))
            if len(p)==5 and p[3]=='transcriptions' and method=='PUT':
                return edit_transcription(con,pid,p[4],b.get('expected_version'),b.get('transcript',''),b.get('memo',''),b.get('summary',''))
            if len(p)==4:
                action=p[3];pr=project(con,pid)
                if action=='validate' and method=='GET':
                    latest={}
                    for x in documents(con,pid):latest[x['kind']]=x
                    return validate(pr['data'],[document(con,x['id']) for x in latest.values()],pr['version'])
                if action=='documents' and method=='GET':return documents(con,pid)
                if action=='transcriptions':
                    if method=='GET':return transcriptions(con,pid)
                    if method=='POST':
                        if b.get('expected_version')!=pr['version']:raise Conflict('원장 버전이 변경되었습니다. 새로고침 후 다시 전사 내용을 등록하세요.')
                        data,session=register_transcript(pr['data'],b.get('text',''),str(b.get('visit_round','1')),memo=b.get('memo',''))
                        saved=save_project(con,pid,data,pr['version'],f'{session["visit_round"]}차 실시간 전사 요약 및 관련 항목 자동 등록')
                        sid=uid()
                        con.execute('INSERT INTO transcriptions(id,project_id,project_version,visit_round,transcript,memo,summary,categories_json,registered_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                            (sid,pid,saved['version'],session['visit_round'],session['transcript'],session['memo'],session['summary'],dumps(session['categories']),dumps(session['registered_paths']),session['created_at'],session['created_at']))
                        con.execute('INSERT INTO audit_log(project_id,action,detail_json,created_at) VALUES(?,?,?,?)',(pid,'transcription_register',dumps({'transcription_id':sid,'project_version':saved['version'],'evidence_id':session['evidence_id'],'registered_paths':session['registered_paths']}),now()))
                        return {'project':saved,'transcription':{'id':sid,'project_version':saved['version'],**session}}
                if action=='generate' and method=='POST':return generate(con,pid,b.get('kind','all'))
                if action=='transition' and method=='POST':
                    d=transition(pr['data'],b['status'],b['evidence'],b['date'],b['reason'])
                    return save_project(con,pid,d,b['expected_version'],b['reason'],True)
                if action=='prompt' and method=='GET':return prompt_package(pr['data'],pr['version'])
                if action=='backup' and method=='GET':
                    revisions=[{'version':r['version'],'data':json.loads(r['data_json']),'reason':r['reason'],'created_at':r['created_at']} for r in con.execute('SELECT * FROM revisions WHERE project_id=? ORDER BY version',(pid,))]
                    payload={'format':'coordinator-backup-v1','project':pr,'revisions':revisions,'documents':[document(con,r['id']) for r in documents(con,pid)],'transcriptions':transcriptions(con,pid),'audit':[dict(r) for r in con.execute('SELECT * FROM audit_log WHERE project_id=?',(pid,))]}
                    return dumps(payload).encode(),200,'application/json; charset=utf-8','coordinator-backup.json'
        if len(p)>=3 and p[1]=='documents':
            doc=document(con,p[2])
            if len(p)==3 and method=='GET':return doc
            if len(p)==4 and p[3]=='text' and method=='GET':return text_document(doc).encode(),200,'text/plain; charset=utf-8',doc['kind']+'-draft.txt'
            if len(p)==4 and p[3]=='hwpx' and method=='POST':
                t,raw=template(con,b['template_id'])
                if t['id'].startswith('official-') and t['id']!='official-'+doc['kind']:
                    raise ValueError('선택 문서와 공식 양식의 종류가 다릅니다. 해당 차수의 양식을 선택하세요.')
                content=hwpx.fill(raw,t['sha256'],t['mapping'],doc['content']['fields'])
                con.execute('INSERT INTO audit_log(project_id,action,detail_json,created_at) VALUES(?,?,?,?)',(doc['project_id'],'hwpx_export',dumps({'document':doc['id'],'template':t['id'],'original_sha256':t['sha256'],'output_sha256':hashlib.sha256(content).hexdigest()}),now()))
                return content,200,'application/hwp+zip',doc['kind']+'-draft.hwpx'
        if p==['api','templates']:
            if method=='GET':return [{'id':r['id'],'name':r['name'],'sha256':r['sha256'],'mapping_count':len(json.loads(r['mapping_json']))} for r in con.execute('SELECT * FROM templates ORDER BY created_at')]
            if method=='POST':
                name=b['name']
                if not isinstance(name,str) or not name.lower().endswith('.hwpx'):raise ValueError('HWPX 파일만 등록할 수 있습니다.')
                return register_template(con,name,base64.b64decode(b['base64'],validate=True))
        if len(p)==3 and p[1]=='templates':
            t,raw=template(con,p[2])
            if method=='GET':return {**t,**hwpx.inspect(raw)}
            if method=='PUT':
                if b['sha256']!=t['sha256']:raise Conflict('양식 버전이 다릅니다.')
                mapping=b['mapping']
                if not isinstance(mapping,list):raise ValueError('매핑은 배열이어야 합니다.')
                if mapping:hwpx.fill(raw,t['sha256'],mapping,{m['field']:'매핑검증' for m in mapping})
                con.execute('UPDATE templates SET mapping_json=? WHERE id=?',(dumps(mapping),t['id']))
                return {'saved':True,'mapping_count':len(mapping)}
        raise LookupError('없는 API 경로')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--access-token');args=parser.parse_args()
    initialize();server=ThreadingHTTPServer((args.host,args.port),Handler)
    server.allow_lan=not is_loopback_host(args.host)
    server.trust_loopback=True
    server.trusted_hosts={x.strip().lower() for x in (os.environ.get('COORDINATOR_TRUSTED_HOSTS','')+','+os.environ.get('RAILWAY_PUBLIC_DOMAIN','')).split(',') if x.strip()}
    server.access_token=args.access_token if args.access_token is not None else (secrets.token_urlsafe(18) if server.allow_lan else '')
    print(f'Coordinator MVP: http://127.0.0.1:{args.port} | database: {DB}',flush=True)
    if server.allow_lan:
        addresses=lan_addresses()
        access_lines=['스마트제조 코디네이터 모바일 접속 주소','PC와 휴대폰을 같은 Wi-Fi에 연결한 뒤 아래 주소 전체를 휴대폰 브라우저에서 여세요.','']
        if addresses:
            print(f'Mobile URL: http://{addresses[0]}:{args.port}/?token={server.access_token}',flush=True)
            access_lines.append(f'권장 주소: http://{addresses[0]}:{args.port}/?token={server.access_token}')
            for address in addresses[1:]:print(f'Other local URL: http://{address}:{args.port}/?token={server.access_token}',flush=True)
            access_lines.extend(f'대체 주소: http://{address}:{args.port}/?token={server.access_token}' for address in addresses[1:])
        else:print(f'Mobile URL: http://{socket.gethostname()}:{args.port}/?token={server.access_token}',flush=True)
        if not addresses:access_lines.append(f'접속 주소: http://{socket.gethostname()}:{args.port}/?token={server.access_token}')
        (DATA/'mobile-access.txt').write_text('\n'.join(access_lines)+'\n',encoding='utf-8')
        print('같은 Wi-Fi의 휴대폰에서 Mobile URL 전체를 여세요. 주소는 이 실행 중에만 사용하세요.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:server.server_close()
