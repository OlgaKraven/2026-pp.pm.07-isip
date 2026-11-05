"""Prepare individual PostgreSQL lab inputs. No student answers are generated."""
from pathlib import Path
import csv,hashlib,io,json,shutil,zipfile
ROOT=Path(__file__).resolve().parents[1]
NAMES=['Сервис проката оборудования','Заявки ремонтной мастерской','Заказы книжного магазина','Бронирования учебных аудиторий','Сервис доставки обедов','Заказы типографии','Выдача спортивного инвентаря','Ремонт компьютерной техники','Заказы цветочной мастерской','Заявки управляющей компании','Прокат туристического снаряжения','Заказы мебельного цеха','Регистрация учебных мероприятий','Заказы фотоцентра','Заявки транспортной службы']
CASES=[('excess','Избыточное право удаления'),('index','Отсутствует индекс поиска'),('port','Ошибочный порт резервирования'),('path','Каталог копий указывает на файл'),('missing','У роли чтения отсутствует SELECT')]
def make():
 out=[]
 for i,name in enumerate(NAMES,1):
  p=ROOT/'variants'/f'variant-{i:02}';p.mkdir(parents=True,exist_ok=True)
  n=3000+i*120;rows=[]
  for j in range(1,n+1):
   amount=f'{(j*17+i*13)%25000}.{(j*7)%100:02}'
   rows.append([str(j),f'REF-{j:06}',amount,['new','done','hold'][j%3]])
  total=sum(int(r[2].replace('.','')) for r in rows)
  digest=hashlib.md5('\n'.join('|'.join(r) for r in rows).encode()).hexdigest()
  case,title=CASES[(i-1)%5]
  c=dict(variant=i,subject=name,database=f'pp07_v{i:02}',port=55470,backup_port=55471 if case=='port' else 55470,backup_dir='orders.csv' if case=='path' else 'backups',backup_time=f'18:{i:02}',rows=n,total=f'{total//100}.{total%100:02}',digest=digest,incident=case,incident_title=title,rto_seconds=120,rpo_hours=24)
  (p/'config.json').write_text(json.dumps(c,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  with (p/'orders.csv').open('w',newline='',encoding='utf-8') as f:
   w=csv.writer(f,lineterminator='\n');w.writerow(['id','reference','amount','status']);w.writerows(rows)
  shutil.copyfile(ROOT/'lab/lab.ps1',p/'lab.ps1')
  (p/'README.md').write_text(f'# Вариант {i:02} — {name}\n\nОткрыть методические рекомендации, раздел «Подготовка папки». Работать только с БД `{c["database"]}` и портом {c["port"]}.\n\n`orders.csv` — исходные учебные данные. `config.json` — паспорт и параметры. `lab.ps1` — читаемый инструмент эксплуатации; сценарий не исправляет инцидент автоматически. Каталоги `.local/` и `backups/` создаются при работе и не публикуются.\n',encoding='utf-8')
  (p/'.gitignore').write_text('.local/\nbackups/\n*.partial\n*.dump\n*.dump.json\n',encoding='utf-8')
  out.append(c)
 (ROOT/'content/variants.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('Prepared',len(out),'individual input sets')
if __name__=='__main__':make()
