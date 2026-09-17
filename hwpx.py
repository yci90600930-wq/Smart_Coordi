"""Preserve all HWPX archive members; edit only selected text spans in sections."""
import hashlib
import html
import io
import re
import zipfile
import xml.etree.ElementTree as ET

TEXT = re.compile(rb'<(?P<tag>[A-Za-z_][\w.-]*:t)\b(?P<attrs>[^>]*?)(?:\s*/>|>(?P<body>.*?)</(?P=tag)\s*>)',re.S)
EMPTY_RUN = re.compile(rb'<(?P<tag>[A-Za-z_][\w.-]*:run)\b(?P<attrs>[^>]*?)(?:\s*/>|>\s*</(?P=tag)\s*>)',re.S)
MAX_ARCHIVE=30*1024*1024
MAX_EXPANDED=120*1024*1024

def archive(raw):
    if len(raw)>MAX_ARCHIVE:raise ValueError('HWPX 파일은 30MB 이하여야 합니다.')
    z=zipfile.ZipFile(io.BytesIO(raw))
    infos=z.infolist(); names=[i.filename for i in infos]
    if len(names)!=len(set(names)) or len(names)>4000:raise ValueError('중복 또는 과도한 ZIP 항목')
    if any('..' in n.split('/') or n.startswith(('/', '\\')) or ':' in n for n in names):raise ValueError('안전하지 않은 ZIP 경로')
    if any(i.flag_bits&1 for i in infos):raise ValueError('암호화된 양식은 지원하지 않습니다.')
    if sum(i.file_size for i in infos)>MAX_EXPANDED:raise ValueError('압축해제 크기 제한을 초과했습니다.')
    if 'mimetype' not in names or z.read('mimetype').strip()!=b'application/hwp+zip':raise ValueError('HWPX mimetype이 올바르지 않습니다.')
    if not any(re.fullmatch(r'Contents/section\d+\.xml',n) for n in names):raise ValueError('section XML이 없습니다.')
    for n in names:
        if n.endswith(('.xml','.hpf')):
            b=z.read(n)
            if b'<!DOCTYPE' in b.upper() or b'<!ENTITY' in b.upper():raise ValueError('외부 엔티티가 있는 XML은 지원하지 않습니다.')
            ET.fromstring(b)
    if z.testzip():raise ValueError('ZIP 무결성 오류')
    return z

def nodes_for(part,raw):
    result=[]
    for m in TEXT.finditer(raw):
        body=m.group('body') or b''
        markup=b''.join(re.findall(rb'<[^>]+>',body))
        editable=not markup or all(re.fullmatch(rb'<[\w.-]+:(?:tab|fwSpace|nbSpace)\b[^>]*/>',tag) for tag in re.findall(rb'<[^>]+>',body))
        result.append({'part':part,'text':html.unescape(body.decode('utf-8')),'editable':bool(editable),'start':m.start(),'end':m.end(),'tag':m.group('tag').decode(),'attrs':m.group('attrs').decode(),'markup':markup.decode(),'empty_run':False})
    for m in EMPTY_RUN.finditer(raw):
        result.append({'part':part,'text':'','editable':True,'start':m.start(),'end':m.end(),'tag':m.group('tag').decode(),'attrs':m.group('attrs').decode(),'markup':'','empty_run':True})
    result.sort(key=lambda n:n['start'])
    for i,n in enumerate(result):n['index']=i
    return result

def inspect(raw):
    z=archive(raw); nodes=[]
    for n in z.namelist():
        if re.fullmatch(r'Contents/section\d+\.xml',n):nodes.extend(nodes_for(n,z.read(n)))
    return {'sha256':hashlib.sha256(raw).hexdigest(),'nodes':[{k:v for k,v in n.items() if k not in ('start','end','tag','attrs','markup')} for n in nodes],'parts':z.namelist()}

def fill(raw,sha256,mapping,fields):
    if hashlib.sha256(raw).hexdigest()!=sha256:raise ValueError('원본 해시가 변경되었습니다. 새 양식으로 등록하세요.')
    z=archive(raw)
    if not isinstance(mapping,list) or not mapping:raise ValueError('양식 입력 위치 매핑이 없습니다.')
    if len(mapping)>5000:raise ValueError('매핑 개수 제한 초과')
    changes={};seen=set()
    for m in mapping:
        part=m['part'];index=m['index'];field=m['field']
        if not isinstance(index,int) or index<0:raise ValueError('텍스트 위치 오류')
        if (part,index) in seen:raise ValueError('한 텍스트 위치에 중복 매핑이 있습니다.')
        seen.add((part,index))
        if not re.fullmatch(r'Contents/section\d+\.xml',part) or part not in z.namelist():raise ValueError('허용되지 않은 XML 입력 위치')
        ns=nodes_for(part,z.read(part))
        if index>=len(ns):raise ValueError('텍스트 위치가 존재하지 않습니다.')
        n=ns[index]
        if not n['editable'] or n['text']!=m.get('expected'):raise ValueError('원본 예상 텍스트가 다르거나 복합 텍스트 노드입니다.')
        if field not in fields:raise ValueError('문안 필드가 없습니다: '+str(field))
        text=str(fields[field])
        if m.get('clear') is True:text=''
        if 'line' in m:
            line=m['line'];lines=text.splitlines()
            if not isinstance(line,int) or line<0:raise ValueError('줄 매핑 오류')
            text=lines[line] if line<len(lines) else ''
        limit=m.get('max_chars',12000)
        if not isinstance(limit,int) or not 1<=limit<=50000 or len(text)>limit:raise ValueError('양식 입력 길이를 초과했습니다. 매핑 또는 문안을 확인하세요.')
        if any(ord(ch)<32 and ch not in '\n\r\t' for ch in text):raise ValueError('XML에 사용할 수 없는 제어문자')
        inner=html.escape(text,quote=False)+n['markup']
        if n['empty_run']:
            prefix=n['tag'].split(':')[0]
            inner=f'<{prefix}:t>{inner}</{prefix}:t>'
        replacement=f'<{n["tag"]}{n["attrs"]}>{inner}</{n["tag"]}>'.encode('utf-8')
        changes.setdefault(part,[]).append((n['start'],n['end'],replacement))
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as dst:
        dst.comment=z.comment
        for info in z.infolist():
            content=z.read(info.filename)
            for start,end,repl in sorted(changes.get(info.filename,[]),reverse=True):content=content[:start]+repl+content[end:]
            if info.filename in changes:ET.fromstring(content)
            dst.writestr(info,content)
    result=out.getvalue();archive(result)
    return result
