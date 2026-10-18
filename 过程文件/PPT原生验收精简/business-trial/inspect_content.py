import hashlib, json, zipfile
from pathlib import Path
from lxml import etree

root=Path(__file__).resolve().parent
source=root.parent/'sample.pptx'
ns={'p':'http://schemas.openxmlformats.org/presentationml/2006/main', 'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
with zipfile.ZipFile(source) as z:
    slides=[]
    for name in sorted(n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')):
        xml=etree.fromstring(z.read(name))
        slides.append({'part':name, 'texts':xml.xpath('//a:t/text()', namespaces=ns), 'native_tables':len(xml.xpath('//a:tbl',namespaces=ns)), 'pictures':len(xml.xpath('//p:pic',namespaces=ns)), 'text_shapes':len(xml.xpath('//p:sp',namespaces=ns)), 'fonts':sorted(set(xml.xpath('//@typeface')))})
report={'source':str(source), 'source_sha256_after':hashlib.sha256(source.read_bytes()).hexdigest(), 'slides':slides}
(root/'content.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
