"""Retain selected genuine outputs; they are labelled text, never mock screenshots."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
course=json.loads((ROOT/'content/course.json').read_text(encoding='utf-8'))
actual=json.loads((ROOT/'work/runtime-results.json').read_text(encoding='utf-8'))
def block(title,text):return dict(title=title,text=text,kind='code')
def add(prefix,title,text):
 page=next(p for p in course['guide'] if p['title'].startswith(prefix))
 page['blocks'].append(block(title,text))
add('7.','Фактический вывод варианта 01 после исправления',actual[0]['verify'])
for prefix,idx in [('6А.',0),('6Б.',1),('6Д.',4)]:
 result=actual[idx]
 # Original execution output is copied without inventing an application UI.
 before=result['before'].split('BACKUP PORT')[0].strip()
 after=result['after'].split('BACKUP PORT')[0].strip()
 add(prefix,f'Фактический вывод варианта {idx+1:02} до исправления',before)
 add(prefix,f'Фактический вывод варианта {idx+1:02} после исправления',after)
(ROOT/'content/course.json').write_text(json.dumps(course,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Added genuine SQL output examples')
