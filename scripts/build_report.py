"""Adapt a copy of the retained common report master; leave the master unchanged."""
from copy import deepcopy
import hashlib,json,shutil,zipfile
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn
from docx.shared import Mm,Pt,RGBColor
from docx.enum.table import WD_ROW_HEIGHT_RULE
import report_parts as parts
ROOT=Path(__file__).resolve().parents[1]
MASTER=ROOT/'forms/template/Отчет о выполнении.docx'
def text(e):return ''.join(t.text or '' for t in e.iter(qn('w:t')))
def rows(table,labels):
 original=deepcopy(table.rows[1]._tr)
 while len(table.rows)<len(labels)+1:table._tbl.append(deepcopy(original))
 while len(table.rows)>len(labels)+1:table._tbl.remove(table.rows[-1]._tr)
 for i,label in enumerate(labels,1):
  cell=table.rows[i].cells[0];ts=cell._tc.xpath('.//w:t');ts[0].text=label
  for t in ts[1:]:t.text=''
 for row in table.rows:row.height=Mm(12);row.height_rule=WD_ROW_HEIGHT_RULE.AT_LEAST
def build():
 assert hashlib.sha256(MASTER.read_bytes()).hexdigest()=='5b91286458395ae589ded859021f287ce50cca1148cc5b29226b6fb1cb5373c4'
 out=ROOT/'forms/Отчет о выполнении.docx';shutil.copyfile(MASTER,out);doc=Document(out)
 d=json.loads((ROOT/'content/course.json').read_text(encoding='utf-8'))
 for c in doc.element.xpath('.//w:sdt'):
  tag=c.find('w:sdtPr/w:tag',c.nsmap)
  if tag is not None and tag.get(qn('w:val'))=='practice_name':
   ts=list(c.iter(qn('w:t')));ts[0].text='Соадминистрирование и автоматизация баз данных и серверов (ПМ.07)'
   for t in ts[1:]:t.text=''
 rows(doc.tables[0],['Номер и предметная область','Операция, пользователи и назначение журнала','Исходный ZIP, CSV и паспорт','rows, total и digest своего варианта','Инцидент и критерии RTO/RPO'])
 rows(doc.tables[1],['Windows и Windows PowerShell','PostgreSQL и путь к утилитам','Рабочая папка, адрес и порт','Word, PowerPoint и Git'])
 rows(doc.tables[2],['Папка и номер образца','БД и роль reader','Количество, сумма и digest','Инцидент и его ограниченная правка','Расписание и независимое хранение'])
 rows(doc.tables[-1],['Исходные материалы и импорт','Сервер и инфраструктура','Инцидент до и после','Чтение и отказ DELETE','Копия, паспорт и SHA-256','FAIL и код завершения','Восстановление: три контроля','Время и доступ восстановленной БД','Повреждённый архив отклонён','Автоматический триггер и OK','Ежедневный режим и XML','Чистый повтор и регламент','Репозиторий, формы и презентация'])
 # Keep the mapping table's heading with it on a fresh page.
 doc.tables[2]._tbl.getprevious().get_or_add_pPr().append(parts.el('pageBreakBefore'))
 body=doc.element.body;children=list(body)
 start=next(i for i,e in enumerate(children) if text(e)=='Этап выполнения работы')
 end=next(i for i,e in enumerate(children) if text(e)=='Итоговая проверка и сдача');anchor=children[end]
 for e in children[start:end]:body.remove(e)
 parts.CONTROL_ID=10000;fig=0
 for index,stage in enumerate(d['report']['sections'],1):
  first=len(list(body))-1
  parts.heading(doc,stage['title'],level=2,new_page=index>1)
  doc.add_paragraph(stage['prompt'])
  for label,tag,n in [('Исходные данные и ожидаемый результат','expected',2),('Выполненные действия','actions',3),('Фактический результат и проверка','actual',2),('Вывод по этапу и объяснение расхождений','conclusion',2)]:parts.response(doc,label,f'pp07_s{index}_{tag}',n)
  doc.add_page_break();p=doc.add_paragraph('Подтверждения этапа приведены на рис. ')
  for j,caption in enumerate(stage['screenshots']):
   if j:p.add_run(', ')
   parts.field(p,f'REF pp07_fig_{fig+j+1} \\h',str(fig+j+1))
  p.add_run('. Вставить собственные результаты, сохранив подписи.')
  for caption in stage['screenshots']:
   fig+=1;parts.figure_slot(doc,caption,f'pp07_picture_{fig}',fig,f'pp07_fig_{fig}')
  generated=list(body)[first:-1]
  for e in generated:body.remove(e);anchor.addprevious(e)
 for index,c in enumerate(doc.element.xpath('.//w:sdt'),30000):c.find('w:sdtPr/w:id',c.nsmap).set(qn('w:val'),str(index))
 for lvl in doc.part.numbering_part.element.findall('.//'+qn('w:lvl')):
  suffix=lvl.find(qn('w:suff'))
  if suffix is not None:suffix.set(qn('w:val'),'nothing')
  rp=lvl.find(qn('w:rPr'))
  if rp is None:rp=parts.el('rPr');lvl.append(rp)
  fonts=rp.find(qn('w:rFonts'))
  if fonts is None:fonts=parts.el('rFonts');rp.append(fonts)
  for attr in ['ascii','hAnsi','eastAsia','cs']:fonts.set(qn('w:'+attr),'Times New Roman')
  for attr in ['asciiTheme','hAnsiTheme','eastAsiaTheme','cstheme']:fonts.attrib.pop(qn('w:'+attr),None)
 for paragraph in doc.paragraphs:
  if paragraph.style.name in ['Heading 1','Heading 2','Heading 3'] and paragraph.runs:paragraph.runs[0].text=' '+paragraph.runs[0].text
  if paragraph.text=='Состав передаваемых материалов':paragraph.paragraph_format.page_break_before=True
 doc.core_properties.title='Отчет о выполнении';doc.core_properties.subject='ПМ.07'
 doc.core_properties.author=doc.core_properties.last_modified_by='';doc.core_properties.comments=''
 doc.save(out)
 # Preserve the original master styles, relationships and resources exactly.
 with zipfile.ZipFile(out) as z:edited={n:z.read(n) for n in z.namelist()}
 with zipfile.ZipFile(MASTER) as z:original={n:z.read(n) for n in z.namelist()}
 allowed={'word/document.xml','word/numbering.xml','docProps/core.xml'}
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  for name,value in original.items():
   info=zipfile.ZipInfo(name,(2026,11,5,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,edited[name] if name in allowed else value)
 print('Adapted common master:',len(d['report']['sections']),'stages,',fig,'figure placeholders')
if __name__=='__main__':build()
