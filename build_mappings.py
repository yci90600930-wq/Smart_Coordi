"""Explicit mappings inspected against the bundled official templates; run once when templates change."""
import json
from pathlib import Path
import hwpx

ROOT=Path(__file__).resolve().parent

def build(kind):
    nodes=hwpx.inspect((ROOT/'templates'/f'{kind}.hwpx').read_bytes())['nodes'];mapping=[]
    def add(i,field,**extra):
        n=nodes[i]
        mapping.append({'part':n['part'],'index':i,'expected':n['text'],'field':field,'max_chars':12000,**extra})
    def section(indices,key):
        # Place full text in first paragraph and clear only the remaining input examples.
        add(indices[0],'sections.'+key)
        for i in indices[1:]:add(i,'empty')
    if kind=='result':
        for i,f in {6:'pending.general',8:'company.name',10:'company.representative',12:'company.business_no',14:'company.phone',16:'contact.organization',17:'contact.coordinator',18:'pending.general',19:'contact.email',51:'implementation.report_date',53:'signature.representative',55:'signature.coordinator'}.items():add(i,f)
        for indexes,k in [([26,27,28,29],'company'),([31,32,33],'purpose'),([35,36,37,38,39,40],'kpi'),([42,43],'assets'),([45,46],'data'),([48],'opinion')]:section(indexes,k)
    elif kind.startswith('visit'):
        shift=4 if kind=='visit1' else 0
        for i,f in {6:'company.name',10:'company.representative',12:'company.business_no',14:'company.phone',16:'company.coordinator',18:'pending.general',20:'visit.round',22:'visit.date',24:'visit.time',26:'visit.duration',28:'pending.general',32:'sections.summary',35:'pending.general',37:'sections.next',42:'company.representative',44:'company.coordinator',48:'visit.date',52:'signature.representative',54:'signature.coordinator'}.items():add(i+shift,f)
        off=5 if kind=='visit1' else 0
        for i,f in {58:'company.name',60:'visit.date',62:'company.business_no',64:'visit.round',66:'signature.representative',68:'signature.coordinator'}.items():add(i+off,f)
        if kind=='visit1':
            for indexes,k in [([76],'interview'),([79],'process'),([81,82],'baseline'),([84,85],'recording'),([88],'data'),([90],'cause'),([92],'inspection'),([94],'safety'),([96],'staff'),([98,99,100,101],'opinion'),([103,104],'photos')]:section(indexes,k)
        elif kind=='visit2':
            for indexes,k in [([70,71,72,73],'previous'),([75],'observation'),([78,79,80],'cause'),([82,83],'improvement'),([87,88,89,90],'priority'),([92,93],'recording'),([97,98,99],'assets'),([102,103],'reference'),([105,106],'photos')]:section(indexes,k)
        else:
            for indexes,k in [([70,71],'previous'),([74],'type'),([77,78,79,80,81,82],'improvement'),([85],'assets'),([88],'budget'),([91,92],'submission'),([94],'aftercare'),([96,97],'photos')]:section(indexes,k)
    else:
        fields={8:'company.application_type',10:'company.application_field',12:'company.name',14:'company.business_no',16:'company.representative',18:'company.phone',20:'pending.general',22:'pending.general',24:'company.address',36:'budget.government',38:'budget.cash',40:'budget.inkind',41:'budget.self_total',42:'budget.total',61:'hw.method',62:'hw.name',63:'hw.model',64:'hw.quantity',65:'pending.quote',66:'pending.quote',67:'hw.amount',70:'hw.supplier',72:'sw.method',73:'empty',74:'empty',75:'sw.name',76:'sw.model',77:'sw.quantity',78:'pending.quote',79:'pending.quote',80:'sw.amount',83:'sw.supplier',92:'hw.schedule',93:'empty',99:'sw.schedule',110:'sections.company',113:'sections.preparation',115:'sections.asis',118:'sections.process',120:'company.products',122:'pending.general',125:'sections.products',126:'pending.general',129:'pending.general',130:'pending.general',135:'sections.hw',137:'sections.hw',139:'hw.schedule',141:'sections.aftercare',144:'sections.kpi',152:'sections.sw',155:'sections.aftercare',157:'sections.aftercare',160:'sections.kpi',163:'pending.quote',166:'pending.quote',168:'pending.general',170:'pending.general',171:'sw.url',172:'pending.general'}
        for i,f in fields.items():add(i,f)
    (ROOT/'templates'/f'{kind}.mapping.json').write_text(json.dumps(mapping,ensure_ascii=False,indent=2),encoding='utf-8')
    return len(mapping)

if __name__=='__main__':
    for k in ['visit1','visit2','visit3','plan','result']:print(k,build(k))
