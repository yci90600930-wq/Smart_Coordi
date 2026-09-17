const money = v => Number(String(v||'').replace(/[^0-9.-]/g,'')) || 0;
const norm = s => String(s||'').replace(/\u00a0/g,' ').replace(/[\t ]+/g,' ').trim();
const HW=['설비','장비','센서','PLC','plc','태블릿','PC','컴퓨터','바코드','프린터','카메라','로봇','스캐너','서버','게이트웨이','키오스크','모니터','단말'];
const SW=['MES','mes','ERP','erp','소프트웨어','S/W','SW','프로그램','시스템','생산관리','품질관리','재고관리','공정관리','모니터링','대시보드','라이선스','개발'];
const TOTAL_WORDS=['합계','총액','견적금액','공급가액','소계','부가세','vat','VAT'];

export function classifyItem(name=''){
  if(SW.some(k=>name.includes(k))) return 'S/W';
  if(HW.some(k=>name.includes(k))) return 'H/W';
  return '기타';
}

export function parseQuoteText(text){
  const lines=String(text||'').split(/\r?\n/).map(norm).filter(Boolean);
  const items=[];
  let explicitTotal=0, vat=0, supply=0;
  for(const line of lines){
    const nums=[...line.matchAll(/(?:\d{1,3}(?:,\d{3})+|\d{4,})(?:\.\d+)?/g)].map(m=>({raw:m[0],value:money(m[0]),index:m.index}));
    if(!nums.length) continue;
    const lower=line.toLowerCase();
    if(/부가세|vat/.test(lower)){vat=Math.max(vat,...nums.map(x=>x.value));continue;}
    if(/공급가액/.test(line)){supply=Math.max(supply,...nums.map(x=>x.value));continue;}
    if(/총액|견적금액|합계/.test(line)){explicitTotal=Math.max(explicitTotal,...nums.map(x=>x.value));continue;}
    if(TOTAL_WORDS.some(k=>line.includes(k))) continue;
    const amount=nums[nums.length-1].value;
    if(amount<=0) continue;
    let name=line.slice(0,nums[0].index).replace(/^\s*\d+[.)\-\s]*/,'').replace(/[|:：]+$/,'').trim();
    if(name.length<2) name=line.replace(nums.map(x=>x.raw).join('|'),'').trim();
    const quantity=guessQty(line,nums);
    const unitPrice=nums.length>=2?nums[nums.length-2].value:(quantity>1?Math.round(amount/quantity):amount);
    items.push({name:name||'견적 항목',category:classifyItem(name),model:'',qty:quantity,unit_price:unitPrice,amount,source_line:line});
  }
  const dedup=dedupe(items);
  const itemSum=dedup.reduce((a,b)=>a+money(b.amount),0);
  const total=explicitTotal || (supply&&vat?supply+vat:supply||itemSum);
  return {items:dedup,total,supply,vat,raw_text:text};
}

function guessQty(line, nums){
  const q=line.match(/(?:수량|qty|QTY)\s*[:：]?\s*(\d{1,3})/i); if(q) return Math.max(1,Number(q[1]));
  if(nums.length>=3){const candidate=nums[0].value;if(candidate>0&&candidate<1000)return candidate;}
  return 1;
}
function dedupe(items){
  const seen=new Set(); return items.filter(x=>{const k=`${x.name}|${x.amount}`;if(seen.has(k))return false;seen.add(k);return true;});
}

export async function extractQuote(file,onProgress=()=>{}){
  const name=file.name.toLowerCase();
  if(name.endsWith('.xlsx')||name.endsWith('.xls')||name.endsWith('.csv')) return extractSpreadsheet(file,onProgress);
  if(name.endsWith('.pdf')) return extractPdf(file,onProgress);
  if(file.type.startsWith('image/')||/\.(png|jpg|jpeg|webp|bmp)$/i.test(name)) return extractImage(file,onProgress);
  if(name.endsWith('.txt')) return parseQuoteText(await file.text());
  throw new Error('지원 형식: PDF, 이미지(PNG/JPG), Excel(XLSX/XLS/CSV), TXT');
}

async function extractSpreadsheet(file,onProgress){
  onProgress('Excel 견적서를 읽는 중입니다.');
  const XLSX=await import('https://cdn.jsdelivr.net/npm/xlsx@0.18.5/+esm');
  const wb=XLSX.read(await file.arrayBuffer(),{type:'array'});
  const text=wb.SheetNames.map(n=>XLSX.utils.sheet_to_csv(wb.Sheets[n],{FS:'\t'})).join('\n');
  return parseQuoteText(text);
}

async function extractPdf(file,onProgress){
  onProgress('PDF 텍스트를 분석하는 중입니다.');
  const pdfjs=await import('https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.min.mjs');
  pdfjs.GlobalWorkerOptions.workerSrc='https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.worker.min.mjs';
  const pdf=await pdfjs.getDocument({data:new Uint8Array(await file.arrayBuffer())}).promise;
  let text='';
  for(let p=1;p<=pdf.numPages;p++){
    const page=await pdf.getPage(p);const c=await page.getTextContent();
    text+='\n'+c.items.map(x=>x.str).join(' ');
  }
  if(text.replace(/\s/g,'').length>=40) return parseQuoteText(text);
  onProgress('스캔 PDF로 판단되어 OCR을 수행합니다. 시간이 걸릴 수 있습니다.');
  text='';
  for(let p=1;p<=Math.min(pdf.numPages,8);p++){
    onProgress(`OCR 처리 중 ${p}/${Math.min(pdf.numPages,8)} 페이지`);
    const page=await pdf.getPage(p);const viewport=page.getViewport({scale:1.8});
    const canvas=document.createElement('canvas');canvas.width=viewport.width;canvas.height=viewport.height;
    await page.render({canvasContext:canvas.getContext('2d'),viewport}).promise;
    text+='\n'+await ocrCanvas(canvas,onProgress);
  }
  return parseQuoteText(text);
}

async function extractImage(file,onProgress){
  onProgress('이미지 견적서 OCR을 준비하는 중입니다.');
  const bmp=await createImageBitmap(file);const canvas=document.createElement('canvas');canvas.width=bmp.width;canvas.height=bmp.height;canvas.getContext('2d').drawImage(bmp,0,0);
  const text=await ocrCanvas(canvas,onProgress);return parseQuoteText(text);
}

async function ocrCanvas(canvas,onProgress){
  const {createWorker}=await import('https://cdn.jsdelivr.net/npm/tesseract.js@5/+esm');
  const worker=await createWorker('kor+eng',1,{logger:m=>{if(m.status)onProgress(`${m.status} ${m.progress?Math.round(m.progress*100)+'%':''}`)}});
  const {data}=await worker.recognize(canvas);await worker.terminate();return data.text||'';
}

export function quoteTotals(items){
  const hw=items.filter(x=>x.category==='H/W').reduce((a,b)=>a+money(b.amount),0);
  const sw=items.filter(x=>x.category==='S/W').reduce((a,b)=>a+money(b.amount),0);
  const other=items.filter(x=>x.category==='기타').reduce((a,b)=>a+money(b.amount),0);
  const total=hw+sw+other;
  return {hw,sw,other,total};
}
