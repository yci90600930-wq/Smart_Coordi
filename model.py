"""Canonical business schema, evidence-aware values and CASE 4 seed."""
from copy import deepcopy
from datetime import date
import math

MISSING = {'measurement':'[현장 측정 필요]', 'baseline':'[기초데이터 확보 후 확정]', 'quote':'[견적서 확인 필요]', 'general':'[추가 확인 필요]'}
KINDS = {'verified':'확인된 사실', 'case':'교육 CASE 사실', 'user_statement':'사용자 진술', 'estimate':'추정·체감', 'analysis':'분석 및 판단', 'target':'목표·계획', 'unconfirmed':'추가 확인 필요'}
STATES = ['검토','선정','발주','납품','설치','시범운영','운영','성과측정','성과달성']
DOCS = {'visit1':'1차 수행일지·현장진단표','visit2':'2차 수행일지·현장진단표','visit3':'3차 수행일지·현장진단표','plan':'사업계획서','result':'결과보고서'}

# key, human label, input type, missing reason. Every domain value uses Fact.
GROUPS = {
 'company': {'title':'기업 기본정보','fields':[
 ('name','기업명','text','general'),('representative','대표자','text','general'),('business_no','사업자등록번호','text','general'),('phone','연락처','text','general'),('address','구축지 주소','text','general'),('industry','업종','text','general'),('products','주요제품','text','general'),('employees','종사자 수','number','general'),('revenue','매출액(원)','number','general'),('application_type','신청유형','text','general'),('application_field','신청분야','text','general'),('coordinator','코디네이터','text','general'),('organization','소속','text','general'),('email','이메일','text','general')]},
 'processes': {'title':'제조공정','many':True,'fields':[
 ('name','공정명','text','general'),('input','투입물','text','general'),('equipment','현재 설비','text','general'),('work','작업내용','textarea','general'),('output','산출물','text','general'),('quality','품질기준','text','measurement'),('variables','관리변수','text','general'),('scope','스마트화 범위','text','general')]},
 'problems': {'title':'문제와 원인','many':True,'fields':[
 ('process_id','발생공정 ID','text','general'),('phenomenon','관찰된 문제','textarea','general'),('cause','원인 / 원인가설','textarea','general'),('basis','원인 검증방법','textarea','general'),('priority','우선순위','text','general')]},
 'improvements': {'title':'개선과제','many':True,'fields':[
 ('problem_id','연결 문제 ID','text','general'),('name','개선과제명','text','general'),('goal','개선목표','textarea','general'),('functions','필요한 기능','textarea','general'),('immediate','즉시개선','textarea','general'),('expected','기대효과','textarea','general'),('aftercare','사후관리','textarea','general')]},
 'assets': {'title':'H/W · S/W','many':True,'fields':[
 ('type','구분(H/W 또는 S/W)','text','general'),('name','명칭','text','general'),('model','모델','text','general'),('method','도입형태','text','general'),('improvement_id','개선과제 ID','text','general'),('supplier_id','공급기업 ID','text','general'),('quantity','수량','number','quote'),('amount','공급금액(원)','number','quote'),('spec','필수사양 / 기능','textarea','quote'),('connection','데이터 출력·연계','textarea','quote'),('schedule','구축일정','textarea','general')]},
 'datasets': {'title':'제조데이터','many':True,'fields':[
 ('name','데이터명','text','general'),('process_id','발생공정 ID','text','general'),('collection','수집방법','textarea','general'),('storage','저장·가시화','textarea','general'),('action','분석·개선행동','textarea','general'),('owner','수집담당','text','general'),('frequency','수집주기','text','general')]},
 'kpis': {'title':'KPI','many':True,'fields':[
 ('name','KPI명','text','general'),('category','분야(P/Q/C/D/E)','text','general'),('unit','단위','text','general'),('subject','대상·동일조건','textarea','general'),('baseline','현재값','number','measurement'),('target','목표값','number','baseline'),('actual','실적값','number','measurement'),('direction','방향(높을수록/낮을수록)','text','general'),('formula','산식','text','general'),('denominator','분모 정의','text','general'),('period','측정기간','text','measurement'),('dataset_id','데이터 ID','text','general'),('frequency','측정주기','text','general'),('owner','측정담당','text','general')]},
 'budget': {'title':'사업비','fields':[
 ('government','정부지원금(원)','number','quote'),('cash','자부담 현금(원)','number','quote'),('inkind','자부담 현물(원)','number','quote'),('total','총사업비(원)','number','quote'),('conditions','당해연도 공고 확인','textarea','general')]},
 'suppliers': {'title':'공급기업','many':True,'fields':[
 ('name','공급기업명','text','general'),('business_no','사업자등록번호','text','general'),('url','자료 URL','text','general'),('contact','담당자·연락처','text','general'),('warranty','A/S·유지관리 조건','textarea','quote')]},
 'visits': {'title':'방문·수행정보','many':True,'fields':[
 ('round','차수','text','general'),('date','수행일자','date','general'),('start','시작시간','time','general'),('end','종료시간','time','general'),('interview','면담 원문 / 기록','textarea','general'),('observations','현장관찰','textarea','general'),('recording','현재 기록방식','textarea','general'),('inspection','검사방식','textarea','general'),('safety','안전·환경','textarea','general'),('staff','운영담당 인력','text','general'),('state','당시 구축상태','state','general'),('photos','수행사진 근거','text','general'),('signatures','서명 근거','text','general'),('next','차기수행내용','textarea','general')]},
 'implementation': {'title':'구축·제출상태','fields':[
 ('status','현재 구축상태','state','general'),('date','상태 확인일','date','general'),('report_date','결과보고 작성예정일','date','general'),('submission','제출상태','text','general'),('submitted_at','실제 제출일','date','general'),('change_reason','변경사유','textarea','general')]}
}

def fact(value=None, evidence='', kind='unconfirmed', missing='general'):
    return {'value':value,'evidence':evidence,'kind':kind,'missing':missing}

def value(f):
    return f.get('value') if isinstance(f,dict) else None

def blank_row(group, row_id=None):
    d={k:fact(missing=m) for k,_,_,m in GROUPS[group]['fields']}
    if row_id: d['id']=row_id
    return d

def blank_project(name='새 기업'):
    d={key:[] if group.get('many') else blank_row(key) for key,group in GROUPS.items()}
    d['company']['name']=fact(name,'manual','user_statement')
    d['implementation']['status']=fact('검토','manual','user_statement')
    d.update(mode='field',evidence=[{'id':'manual','title':'직접 입력','type':'statement','locator':'사용자 입력; 원자료 위치를 보완하세요','excerpt':''}],conflicts=[])
    return d

def evidence_for(d,f):
    return next((e for e in d['evidence'] if e['id']==f.get('evidence')),None)

def supported(d,f):
    if value(f) is None or value(f)=='' or f.get('kind')=='unconfirmed': return False
    e=evidence_for(d,f)
    if not e or not e.get('title') or not e.get('locator'):return False
    if f.get('kind')=='verified' and e['type'] not in ('measurement','document'):return False
    if f.get('kind')=='case' and (d.get('mode')!='training' or e['type']!='case'):return False
    return True

def show(d,f,unit='',annotate=True):
    if not supported(d,f): return MISSING.get(f.get('missing'),MISSING['general'])
    v=value(f)
    text=f'{v:,}' if isinstance(v,(int,float)) and not isinstance(v,bool) else str(v)
    if unit: text+=unit
    if annotate and f.get('kind') in ('user_statement','estimate','analysis','target'):
        text+=' ('+KINDS[f['kind']]+')'
    return text

def walk_facts(d):
    for group,spec in GROUPS.items():
        rows=d[group] if spec.get('many') else [d[group]]
        for i,row in enumerate(rows):
            for key,label,typ,missing in spec['fields']:
                yield f'{group}.{i}.{key}' if spec.get('many') else f'{group}.{key}',row[key],typ,label

def validate_shape(d):
    if not isinstance(d,dict) or d.get('mode') not in ('training','field'): raise ValueError('기업 데이터 형식 또는 사례구분이 올바르지 않습니다.')
    for group,spec in GROUPS.items():
        if group not in d: raise ValueError(f'{group} 필드가 없습니다.')
        rows=d[group] if spec.get('many') else [d[group]]
        if not isinstance(rows,list) or len(rows)>100: raise ValueError('항목은 그룹별 최대 100개입니다.')
        ids=[]
        for row in rows:
            if not isinstance(row,dict): raise ValueError('항목은 객체여야 합니다.')
            if spec.get('many'):
                if not isinstance(row.get('id'),str) or not row['id']: raise ValueError('항목 ID가 없습니다.')
                ids.append(row['id'])
            for key,label,typ,_ in spec['fields']:
                f=row.get(key)
                if not isinstance(f,dict) or f.get('kind') not in KINDS or f.get('missing') not in MISSING or not isinstance(f.get('evidence'),str): raise ValueError(f'{label}: 사실구분·근거 형식 오류')
                v=value(f)
                if typ=='number' and v is not None and (isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0): raise ValueError(f'{label}: 0 이상의 유한한 숫자 또는 빈값을 입력하세요.')
                if typ!='number' and v is not None and (not isinstance(v,str) or len(v)>12000): raise ValueError(f'{label}: 텍스트 형식 오류')
                if typ=='state' and v not in (None,'',*STATES): raise ValueError(f'{label}: 알 수 없는 상태')
                if typ=='date' and v:
                    try: date.fromisoformat(v)
                    except ValueError: raise ValueError(f'{label}: YYYY-MM-DD 형식 필요')
        if len(set(ids))!=len(ids): raise ValueError(f'{group}: 중복 ID')
    if not isinstance(d.get('evidence'),list) or len(d['evidence'])>200: raise ValueError('근거 목록 오류')
    ids=[]
    for e in d['evidence']:
        if any(not isinstance(e.get(k),str) for k in ['id','title','type','locator','excerpt']): raise ValueError('근거 형식 오류')
        if not e['id'] or not e['title'] or len(e['excerpt'])>20000: raise ValueError('근거 ID·제목이 필요합니다.')
        if e['type'] not in ('case','statement','document','measurement','analysis','plan'): raise ValueError('근거 종류 오류')
        ids.append(e['id'])
    if len(set(ids))!=len(ids): raise ValueError('중복 근거 ID')
    if not isinstance(d.get('conflicts'),list): raise ValueError('상충자료 목록 오류')
    for c in d['conflicts']:
        if any(not isinstance(c.get(k),str) for k in ['id','title','detail','resolution']): raise ValueError('상충자료 형식 오류')
    return d

def seed():
    d=blank_project('(주)블루스카이'); d['mode']='training'
    thread='chatgpt-conversation://6aa778eb-06fc-83ee-9797-89ab155ffde7'
    d['evidence']=[
      {'id':'case4','title':'실습 교육 제공 사례 / CASE 4','type':'case','locator':'Google Drive: 1XcEFYKOVvN19Na1LQxKo7Ol2dvh3JVm4 / CASE 4','excerpt':'노후 중고 CNC, 수작업 후처리, 수기 생산자료. CASE 수치는 교육 사례에 한정하여 사용.'},
      {'id':'user-company','title':'기업정보 사용자 입력','type':'statement','locator':thread+' / c91effa7-d7ea-4781-b801-aa3b8dbc5ac4','excerpt':'(주)블루스카이, 윤천일, 123-86-12345, 010-9060-0930, 전남 해남군 화산면 율동리 278번지. SaaS형.'},
      {'id':'user-result','title':'설치·생산실적 사용자 확인','type':'statement','locator':thread+' / 609a8244-b4e8-414c-9f82-b66626f28395','excerpt':'h/w, s/w 납품 설치 완료 된것으로 확인해. kpi는 일 10개 생산됨으로 진행. 설치일·측정기간·생산원장은 미제공.'},
      {'id':'plan','title':'CASE 4 작성된 사업계획서','type':'document','locator':'https://drive.google.com/file/d/1AoCBVV3KKrt8QKtJOWV1-ZG42PlolxSo/view','excerpt':'KPI 6→10개/일, H/W 42,000,000원, S/W 6,000,000원. 총사업비 60,000,000원(현물 12,000,000원 포함). 기존 작성문서이므로 실제 견적·실적과 구분.'},
      {'id':'v3','title':'CASE 4 기존 3차 수행일지','type':'document','locator':'https://drive.google.com/file/d/1bfDpVSrWmogzJJyryqiMYYgBNYUPuBn2/view','excerpt':'2026-09-17 수행일, 설치 전 단계. 제출 완료 / 2026-10-20 기재. 미래 완료표현은 추가확인 필요.'},
      {'id':'process','title':'기존 공정 정리·범위 수정','type':'analysis','locator':thread+' / b8ef990f-0004-4523-a4d7-b6e25651dff6','excerpt':'기존 작성 공정 8단계. H/W는 CNC 밀링, S/W는 전 공정 정보관리. CAM 신규도입 아님. 실제 현장공정 증빙 없음.'},
      {'id':'coordinator','title':'보고서 기본정보 사용자 입력','type':'statement','locator':thread+' / e4dde14a-3ea5-4e28-a9dd-4b032f92e20f','excerpt':'작성일 09월 17일, 소속 블루코어(주), 이메일 yci90600930@gmail.com.'},
      {'id':'design','title':'MVP 개선·데이터 설계안','type':'analysis','locator':'본 MVP의 분석 및 계획; 현장 확인 후 채택','excerpt':'최소 데이터 및 기능요구의 제안이며 설치·운영 실적이 아님.'}]
    def put(group,vals,e='case4',kind='case',id=None):
        row=blank_row(group,id)
        for k,v in vals.items(): row[k]=fact(v,e,kind,row[k]['missing'])
        if GROUPS[group].get('many'):d[group].append(row)
        else:d[group].update({k:row[k] for k in vals})
        return row
    put('company',{'name':'(주)블루스카이','representative':'윤천일','business_no':'123-86-12345','phone':'010-9060-0930','address':'전남 해남군 화산면 율동리 278번지'},'user-company','user_statement')
    put('company',{'industry':'치과보철물 제조','products':'지르코니아·티타늄 치과보철물','employees':1})
    put('company',{'application_type':'개별형','application_field':'공정기술형'},'plan','target')
    put('company',{'organization':'블루코어(주)','email':'yci90600930@gmail.com'},'coordinator','user_statement')
    names=['치과 의뢰 접수 및 작업 준비','설계·가공정보 준비','CAD 설계','CAM 가공데이터 생성','CNC 밀링 가공','후처리·마감','검사·완료','납품']
    for i,n in enumerate(names):
        put('processes',{'name':n,'scope':'H/W 개선 대상 · MES 정보관리' if i==4 else 'MES 생산·작업정보 관리 범위'},'process','analysis',f'p{i+1}')
    d['processes'][4]['equipment']=fact('사업 초기 도입한 중고 CNC 가공장비','case4','case')
    put('problems',{'process_id':'p5','phenomenon':'노후 CNC 가공장비의 정밀도 저하, 생산효율 감소 및 유지관리 부담','priority':'우선과제'},id='problem1')
    d['problems'][0]['cause']=fact('설비 노후화의 영향 가능성. 마모·공구·조건별 영향은 추가 검증 필요','design','analysis')
    put('problems',{'process_id':'p5','phenomenon':'생산량과 작업결과를 수기로 관리함','cause':'공정조건·생산결과 연계 여부 확인 필요'},id='problem2')
    d['problems'][1]['cause']=fact(missing='general')
    put('improvements',{'problem_id':'problem1','name':'CNC 밀링 공정 개선','goal':'핵심 가공공정의 생산 안정성과 정밀도 개선','functions':'5축 건·습식 정밀가공 및 가공이력 확인','immediate':'제품·소재·일자별 생산수량 기록 기준 통일','expected':'생산성 향상 기대. 불량률·비용 절감 수치는 미확정','aftercare':'가동·공구·유지보수 이력을 기록하고 공급기업 A/S 조건 확인'},'design','analysis','imp1')
    put('improvements',{'problem_id':'problem2','name':'생산·작업정보 디지털 관리','goal':'공정별 작업진행과 생산실적의 조회·집계','functions':'작업등록, 생산실적 관리, KPI 집계','immediate':'기존 수기자료의 항목·단위 통일','expected':'생산이력 조회와 비교 기반 확보','aftercare':'입력담당·백업·데이터 반출 조건 확인'},'design','analysis','imp2')
    put('suppliers',{'name':'마닉스','url':'https://manixdental.com/kor/project/zx-5sa/'},'plan','target','supplier1')
    put('suppliers',{'name':'Dentalsoft(덴탈소프트)','url':'https://mes.dentalsoft.co.kr/introduction'},'plan','target','supplier2')
    put('assets',{'type':'H/W','name':'5축 건·습식 덴탈 CNC 밀링기','model':'ZX-5SA','method':'구매','improvement_id':'imp1','supplier_id':'supplier1','quantity':1,'amount':42000000,'spec':'5축 건·습식 덴탈 밀링'},'case4','case','hw1')
    put('assets',{'type':'S/W','name':'Dentalsoft MES','model':'Dentalsoft','method':'SaaS형','improvement_id':'imp2','supplier_id':'supplier2','quantity':1,'amount':6000000},'case4','case','sw1')
    d['assets'][0]['model']=fact('ZX-5SA','plan','target')
    d['assets'][1]['method']=fact('SaaS형','user-company','user_statement')
    put('datasets',{'name':'티타늄 보철물 생산실적','process_id':'p5','collection':'제품·소재·일자·완료수량·작업일수 기록; 설비 자동연계 사양은 별도 확인','storage':'MES 생산실적 집계 및 원장 보관 계획','action':'동일조건의 일평균 생산수량 비교 후 편차 원인 확인','frequency':'작업일별'},'design','analysis','data1')
    k=put('kpis',{'name':'티타늄 치과보철물 일평균 생산수량','category':'P','unit':'개/일','baseline':6},id='kpi1')
    k['target']=fact(10,'plan','target','baseline'); k['actual']=fact(10,'user-result','user_statement','measurement')
    for key,v in {'subject':'티타늄 치과보철물, 동일 제품·동일 작업조건','direction':'높을수록','formula':'측정기간 생산완료수량 합계 ÷ 실제 작업일수','denominator':'실제 작업일수','dataset_id':'data1','frequency':'작업일별 수집·기간 집계'}.items(): k[key]=fact(v,'design','analysis')
    put('budget',{'government':36000000,'cash':12000000,'inkind':12000000,'total':60000000},'plan','target')
    for i,state in enumerate(['검토','선정','선정']):
        put('visits',{'round':str(i+1),'state':state,'recording':'기존 생산량과 작업결과 수기관리','next':['공정관찰·원인변수·기초데이터 확인','최종 H/W·S/W·KPI·사업비 검토','설치일·운영데이터·제출상태 확인'][i]},'v3' if i==2 else 'plan','target',f'visit{i+1}')
        d['visits'][-1]['recording']=fact('기존 생산량과 작업결과 수기관리','case4','case')
        d['visits'][-1]['staff']=fact('대표자 1인 운영. 시스템 교육 및 담당자 확정 필요','case4','case')
    put('implementation',{'status':'설치'},'user-result','user_statement')
    put('implementation',{'report_date':'2026-09-17'},'coordinator','target')
    d['conflicts']=[
      {'id':'conflict-state','title':'3차 수행일지와 결과보고서 구축상태 상충','detail':'기존 3차는 설치 전, 이후 사용자 진술은 설치 완료. 설치일과 문서 기준일 확인 필요. 과거 일지를 소급 덮어쓰지 않음.','resolution':''},
      {'id':'conflict-submit','title':'미래 날짜의 제출완료 기재','detail':'기존 3차에 제출 완료 / 2026-10-20 기재. 실제 제출증빙 확보 전 현재 원장에는 완료를 입력하지 않음.','resolution':''},
      {'id':'conflict-address','title':'구축지 주소 표기 차이','detail':'사용자 입력은 율동리 278번지, 기존 사업계획서에는 000번지. 사용자 입력을 표시하되 제출 전 주소증빙 대조 필요.','resolution':''}]
    validate_shape(d)
    return deepcopy(d)
