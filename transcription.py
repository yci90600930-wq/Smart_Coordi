"""Rule-based Korean transcript summary and evidence-aware master-data registration."""
from copy import deepcopy
from datetime import datetime, timezone
import re
import uuid

from model import GROUPS, blank_row, fact, value

CATEGORY_LABELS = {
    'processes':'공정', 'problems':'문제', 'causes':'원인',
    'improvements':'개선과제', 'assets':'H/W·S/W', 'datasets':'제조데이터',
    'kpis':'KPI', 'budget':'사업비', 'suppliers':'공급기업',
    'status':'구축상태', 'company':'기업정보', 'other':'기타 확인'
}

KEYWORDS = {
    'processes':('공정','작업 순서','가공','검사','포장','출하','생산 과정','직조','편직','봉조','봉제'),
    'problems':('문제','애로','불량','지연','고장','멈춤','멈추','수기','느리','부족','오류','재작업','인건비','원가상승','원가 상승','경쟁력 약화','불가능','이루어지지'),
    'causes':('원인','때문','의존','노후','마모','숙련도','편차','내부 인력','수작업','인력으로'),
    'improvements':('개선','자동화','도입 필요','도입을 계획','구축 필요','표준화','디지털화','바꾸고','해결','교체','순차적으로'),
    'assets':('장비','설비','기계','편직기','봉조기','cnc','센서','plc','mes','erp','프로그램','소프트웨어','하드웨어','s/w','h/w'),
    'datasets':('데이터','기록','수집','저장','로그','이력','엑셀','작업일보'),
    'kpis':('kpi','생산량','불량률','가동률','리드타임','납기','생산성','목표'),
    'budget':('사업비','견적','금액','가격','단가','국비','자부담','현물','원입니다','만원','억 원','억원'),
    'suppliers':('공급기업','공급업체','납품업체','제조사','대리점','a/s','유지보수'),
    'status':('검토','선정','발주','납품','설치','시범운영','운영중','성과측정','성과달성'),
    'company':('기업명','대표자','주소','업종','주요제품','특화 상품','제품','종사자','근무','매출','창업')
}

AUTO_GROUPS = {'processes','problems','causes','improvements','assets','datasets','kpis'}
CATEGORY_PRIORITY = tuple(CATEGORY_LABELS)
FILLERS = ('이렇게 듣는 거예요','이렇게 듣는 거예요.','말씀드리면','그러니까','그냥')
BREAK_BEFORE = (
    '그래서','따라서','하지만','다만','연간 매출','공정 자동화를 위해','직접 기계장비',
    '현재는','향후','양말 생산의 핵심 공정','하드웨어는','소프트웨어는'
)
BREAK_AFTER = ('있으나','있으며','있어','진행하고','계획입니다','상황입니다','하고요','있습니다')

def _clean_text(text):
    text=re.sub(r'\s+',' ',text.strip())
    for filler in FILLERS:text=text.replace(filler,' ')
    return re.sub(r'\s+',' ',text).strip(' ,')

def _clip(text,limit=125):
    text=re.sub(r'\s+',' ',text).strip(' ,.;')
    if len(text)<=limit:return text
    cut=text.rfind(' ',0,limit)
    return text[:cut if cut>limit//2 else limit].rstrip()+'…'

def _summary_phrase(text):
    text=_clip(text)
    text=re.sub(r'^(그래서|따라서|하지만|다만|현재는|그냥)\s*','',text)
    text=re.sub(r'(?<!\S)([가-힣]{2,})\s+\1(?=[을를이가은는])',r'\1',text)
    text=re.sub(r'^(하드웨어는|소프트웨어는)\s+그\s+',r'\1 ',text)
    text=text.replace('이라고 해가지고 요 부분이',',').replace('라고 해가지고',',')
    text=re.sub(r'대당 단가가 (.+?) 정도 두 대를 하려고 하고요$',r'대당 단가 약 \1, 2대 도입 계획',text)
    text=re.sub(r'(\d+\s*만 원)\s+이게 책정되어 있습니다$',r'\1 책정',text)
    endings=((r'계획하고 있으며$','계획'),(r'로 이어지고 있어$',''),(r'진행하고$','진행'),
        (r'근무하고 있어$','근무'),(r'제조하고 있으나$','제조'),(r'하고 있으며$',''),
        (r'보유하고 있으나$','보유'),(r'하고 있어$',''),(r'있으며$',''),(r'있어$',''))
    for pattern,replacement in endings:text=re.sub(pattern,replacement,text)
    return re.sub(r'\s+',' ',text).strip(' ,.;')

def _sentences(text):
    text=_clean_text(text)
    if not text:return []
    text=re.sub(r'[.!?。]+\s*','\n',text)
    before='|'.join(re.escape(x) for x in sorted(BREAK_BEFORE,key=len,reverse=True))
    text=re.sub(rf'\s+(?=(?:{before})\b)', '\n', text)
    after='|'.join(re.escape(x) for x in sorted(BREAK_AFTER,key=len,reverse=True))
    text=re.sub(rf'({after})\s+(?=[가-힣A-Za-z0-9])',r'\1\n',text)
    raw=[x.strip(' ,') for x in text.splitlines() if x.strip(' ,')]
    result=[]
    for item in raw:
        while len(item)>220:
            cut=item.rfind(' ',0,170)
            if cut<80:cut=170
            result.append(item[:cut].strip(' ,'));item=item[cut:].strip(' ,')
        if item:result.append(item)
    return result

def _category_scores(sentence):
    lowered=sentence.lower();scores={}
    for key,words in KEYWORDS.items():
        hits=[w for w in words if w in lowered]
        if hits:scores[key]=sum(1+min(len(w),10)/10 for w in hits)
    if re.match(r'^(하드웨어|소프트웨어|h/w|s/w)',lowered):scores['assets']=scores.get('assets',0)+6
    if any(x in lowered for x in ('문제','애로','불량','지연','고장','멈추','수기','재작업','불가능','이루어지지')):
        scores['problems']=scores.get('problems',0)+3
    if any(x in lowered for x in ('인건비','원가상승','원가 상승','경쟁력 약화')):scores['problems']=scores.get('problems',0)+5
    if ('내부 인력' in lowered or '수작업' in lowered) and not any(x in lowered for x in ('인건비','원가')):scores['causes']=scores.get('causes',0)+4
    if any(x in lowered for x in ('연간 매출','총 ') ) and any(x in lowered for x in ('근무','매출')):scores['company']=scores.get('company',0)+5
    if '자동화' in lowered and any(x in lowered for x in ('도입','계획','교체')):scores['improvements']=scores.get('improvements',0)+5
    return scores

def classify_transcript(text):
    result=[]
    for sentence in _sentences(text):
        scores=_category_scores(sentence)
        cats=sorted(scores,key=lambda key:(-scores[key],CATEGORY_PRIORITY.index(key))) or ['other']
        result.append({'text':sentence,'categories':cats,'primary_category':cats[0],
            'primary_score':scores.get(cats[0],0)})
    return result

def summarize_transcript(classified):
    grouped={}
    for order,item in enumerate(classified):
        category=item.get('primary_category') or item['categories'][0]
        grouped.setdefault(category,[])
        snippet=_summary_phrase(item['text'])
        if not any(x['text']==snippet for x in grouped[category]):
            grouped[category].append({'text':snippet,'score':item.get('primary_score',0),'order':order})
    lines=[]
    for key in CATEGORY_LABELS:
        if key in grouped and (key!='other' or not any(k!='other' for k in grouped)):
            ranked=sorted(grouped[key],key=lambda x:(-x['score'],x['order']))
            if key=='assets':ranked.sort(key=lambda x:(0 if x['text'].startswith('하드웨어') else 1,-x['score'],x['order']))
            limit=2 if key in ('company','assets') else 1
            lines.append(f'[{CATEGORY_LABELS[key]}]')
            lines.extend('- '+x['text'] for x in ranked[:limit])
    if any(key in grouped for key in ('assets','budget','kpis')):
        lines.append('[추가 확인] 전문용어·모델명·수량·금액은 전사 원문이므로 견적서와 현장자료로 재확인 필요')
    return '\n'.join(lines) or '[추가 확인 필요]'

def _unique_id(prefix, rows):
    existing={x.get('id') for x in rows}
    while True:
        candidate=prefix+'-'+uuid.uuid4().hex[:8]
        if candidate not in existing:return candidate

def _duplicate(rows, field_name, sentence):
    norm=lambda x:re.sub(r'\s+',' ',str(x or '')).strip().lower()
    return any(norm(value(row.get(field_name,{})))==norm(sentence) for row in rows)

def _add_row(data,group,field_name,sentence,evidence_id,registered,extra=None):
    rows=data[group]
    if len(rows)>=100 or _duplicate(rows,field_name,sentence):return
    row=blank_row(group,_unique_id('tr-'+group[:3],rows))
    row[field_name]=fact(sentence,evidence_id,'user_statement')
    for key,f in (extra or {}).items():row[key]=f
    rows.append(row);registered.append(f'{group}.{row["id"]}.{field_name}')

def register_transcript(source,text,visit_round='1',created_at=None,memo=''):
    if not isinstance(text,str) or not text.strip():raise ValueError('전사 내용이 비어 있습니다.')
    if len(text)>20000:raise ValueError('전사 내용은 20,000자 이하여야 합니다.')
    if not isinstance(memo,str) or len(memo)>5000:raise ValueError('현장 메모는 5,000자 이하여야 합니다.')
    if str(visit_round) not in ('1','2','3'):raise ValueError('방문 차수는 1·2·3차 중 하나여야 합니다.')
    data=deepcopy(source);stamp=created_at or datetime.now(timezone.utc).isoformat(timespec='seconds')
    evidence_id='transcript-'+uuid.uuid4().hex[:12]
    combined=text.strip()+(('\n'+memo.strip()) if memo.strip() else '')
    classified=classify_transcript(combined);summary=summarize_transcript(classified)
    excerpt='[전사 원문]\n'+text.strip()
    if memo.strip():excerpt+='\n\n[현장 메모]\n'+memo.strip()
    data['evidence'].append({'id':evidence_id,'title':f'{visit_round}차 실시간 전사',
        'type':'statement','locator':f'실시간 전사 {stamp}','excerpt':excerpt})
    registered=[]
    visit=next((v for v in data['visits'] if value(v['round'])==str(visit_round)),None)
    if visit:
        current=value(visit['interview'])
        interview=(current+'\n\n' if current else '')+f'[{stamp} 실시간 전사]\n{text.strip()}'
        if memo.strip():interview+='\n[현장 메모]\n'+memo.strip()
        visit['interview']=fact(interview,evidence_id,'user_statement')
        registered.append(f'visits.{visit["id"]}.interview')
        if not value(visit['observations']):
            visit['observations']=fact('규칙 기반 전사 요약\n'+summary,evidence_id,'analysis')
            registered.append(f'visits.{visit["id"]}.observations')
    candidates={key:[] for key in AUTO_GROUPS}
    for order,item in enumerate(classified):
        category=item.get('primary_category') or item['categories'][0]
        if category in AUTO_GROUPS:candidates[category].append((item.get('primary_score',0),order,item))
    for category in CATEGORY_PRIORITY:
        if category not in candidates:continue
        ranked=sorted(candidates[category],key=lambda x:(-x[0],x[1]))[:2]
        for _,_,item in ranked:
            sentence=_clip(item['text'],180)
            if category=='processes':
                _add_row(data,'processes','name',sentence,evidence_id,registered)
            elif category=='problems':
                _add_row(data,'problems','phenomenon',sentence,evidence_id,registered)
            elif category=='causes':
                _add_row(data,'problems','cause',sentence,evidence_id,registered)
            elif category=='improvements':
                _add_row(data,'improvements','name',sentence,evidence_id,registered)
            elif category=='assets':
                asset_type='S/W' if any(w in sentence.lower() for w in ('mes','erp','프로그램','소프트웨어','s/w')) else 'H/W'
                _add_row(data,'assets','name',sentence,evidence_id,registered,
                    {'type':fact(asset_type,evidence_id,'analysis')})
            elif category=='datasets':
                _add_row(data,'datasets','name',sentence,evidence_id,registered)
            elif category=='kpis':
                _add_row(data,'kpis','name',sentence,evidence_id,registered)
    categories=[]
    for item in classified:
        for category in item['categories']:
            if category not in categories:categories.append(category)
    return data,{'evidence_id':evidence_id,'created_at':stamp,'visit_round':str(visit_round),
        'transcript':text.strip(),'summary':summary,'categories':categories,'classified':classified,
        'memo':memo.strip(),
        'registered_paths':registered,
        'notice':'금액·KPI 수치·구축상태는 발화 원문에만 보존하며 확정 필드나 상태값으로 자동 반영하지 않습니다.'}
