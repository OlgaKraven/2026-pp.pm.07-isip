"""Build with the retained blocks-and-route renderer and reviewed PDF outputs."""
from pathlib import Path
import argparse,hashlib,html,json,shutil,zipfile
from urllib.parse import quote
from design import pdf
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'site';E=html.escape
def link(name,label):return f'<a href="downloads/{quote(name)}">{E(label)}</a>'
def html_page(d,key):
 nav=''.join(f'<a href="{file}" '+('aria-current="page"' if key==sec else '')+f'>{label}</a>' for sec,file,label in [('assignment','index.html','Задание и файлы'),('guide','lessons.html','Методика'),('areas','areas.html','Предметные области')])
 pieces=[]
 specs=d[key]+(d['files'] if key=='assignment' else [])
 for i,p in enumerate(specs,1):
  aid=f'variant-{p["id"]:02}' if 'id' in p else f'section-{i}'
  blocks=[]
  if 'id' in p:blocks.append('<div class="downloads">'+link(p['downloads'][0],f'Скачать стенд варианта {p["id"]:02} (ZIP)')+'</div>')
  if p in d['files']:
   blocks.append('<div class="downloads">'+link('assignment.pdf','Методические рекомендации (PDF)')+link('guide.pdf','Список предметных областей (PDF)')+link('Отчет о выполнении.docx','Отчёт для заполнения (DOCX)')+'</div>')
   blocks.append('<p><a href="https://praktik.mayventra.ru/#practice/4c69500d794d4a388e8d902a31c4f3a1/release">Карточка практики и официальные формы</a> · <a href="https://www.postgresql.org/download/windows/">Установка PostgreSQL для Windows</a> · <a href="https://git-scm.com/downloads/win">Установка Git для Windows</a></p>')
  for n,b in enumerate(p['blocks'],1):
   if b['kind']=='code':body='<pre>'+E(b['text'])+'</pre>'
   elif b['kind']=='image':body=f'<figure><img src="{E(b["path"])}" alt="{E(b["text"])}"><figcaption>{E(b["text"])}</figcaption></figure>'
   else:body=''.join('<p>'+E(t).replace('\n','<br>')+'</p>' for t in b['text'].split('\n\n'))
   blocks.append(f'<div class="step"><span class="number">{n}</span><section class="card"><h3>{E(b["title"])}</h3>{body}</section></div>')
  pieces.append(f'<article class="chapter" id="{aid}"><header class="doc-head"><p class="section-id">ПП ПМ.07</p><h2>{E(p["title"])}</h2></header><div class="steps">'+''.join(blocks)+'</div></article>')
 return '<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+E(d['meta']['title'])+'</title><link rel="stylesheet" href="assets/style.css"></head><body class="'+('subject-areas' if key=='areas' else 'method')+'"><a class="skip" href="#main">К содержанию</a><nav>'+nav+'</nav><main id="main">'+''.join(pieces)+'</main></body></html>'
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--render-pdf',action='store_true');parser.add_argument('--release',action='store_true');args=parser.parse_args()
 d=json.loads((ROOT/'content/course.json').read_text(encoding='utf-8'))
 OUT.mkdir(exist_ok=True);dest=OUT/'downloads';dest.mkdir(exist_ok=True)
 shutil.copytree(ROOT/'assets',OUT/'assets',dirs_exist_ok=True);shutil.copytree(ROOT/'scripts/assets/fonts',OUT/'assets/fonts',dirs_exist_ok=True)
 shutil.copyfile(ROOT/'forms/Отчет о выполнении.docx',dest/'Отчет о выполнении.docx')
 for c in json.loads((ROOT/'content/variants.json').read_text(encoding='utf-8')):
  folder=ROOT/'variants'/f'variant-{c["variant"]:02}'
  with zipfile.ZipFile(dest/(folder.name+'.zip'),'w',zipfile.ZIP_DEFLATED) as z:
   for name in ['lab.ps1','config.json','orders.csv','README.md','.gitignore']:
    info=zipfile.ZipInfo(name,(2026,11,5,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.create_system=3;info.external_attr=0o100644<<16;z.writestr(info,(folder/name).read_text(encoding='utf-8').encode('utf-8'))
 for key,name in [('assignment','index.html'),('guide','lessons.html'),('areas','areas.html')]: (OUT/name).write_text(html_page(d,key),encoding='utf-8')
 source_text=(ROOT/'content/course.json').read_text(encoding='utf-8')+(ROOT/'scripts/design.py').read_text(encoding='utf-8')
 digest=hashlib.sha256(source_text.encode('utf-8')).hexdigest()
 materials=ROOT/'materials';materials.mkdir(exist_ok=True)
 if args.render_pdf:
  for sec,name in [('assignment','assignment.pdf'),('guide','guide.pdf')]:pdf(ROOT,materials/name,d,sec,True)
  (materials/'source-sha256.json').write_text(json.dumps({'source':digest,'files':{name:hashlib.sha256((materials/name).read_bytes()).hexdigest() for name in ['assignment.pdf','guide.pdf']}},indent=2)+'\n')
 pinned=json.loads((materials/'source-sha256.json').read_text());assert pinned['source']==digest,'PDF content changed: render and review again'
 for name,h in pinned['files'].items():
  assert hashlib.sha256((materials/name).read_bytes()).hexdigest()==h;shutil.copyfile(materials/name,dest/name)
 (OUT/'.nojekyll').write_text('')
 (OUT/'manifest.json').write_text(json.dumps({p.relative_to(OUT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.rglob('*') if p.is_file() and p.name!='manifest.json'},ensure_ascii=False,indent=2),encoding='utf-8')
 print('Built full assignment, method, separate area list, 15 input downloads and common report')
if __name__=='__main__':main()
