"""Run individual input sets using one isolated cluster. Preserve complete transcripts."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,shutil,subprocess,time,tempfile
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'work';WORK.mkdir(exist_ok=True)
PGBIN=Path('C:/Program Files/PostgreSQL/18/bin')
events=[]
def run(args,expected=0,env=None):
 with tempfile.TemporaryFile() as f:
  p=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,env=env,timeout=80)
  f.seek(0);text=f.read().decode('utf-8',errors='replace').strip()
 events.append(dict(command=[str(x) for x in args],code=p.returncode,output=text))
 if p.returncode!=expected:raise RuntimeError(text)
 return text
def ps(folder,action,*extra,expected=0):return run(['C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe','-NoProfile','-File',str(folder/'lab.ps1'),'-Action',action,*extra],expected)
def main():
 variants=json.loads((ROOT/'content/variants.json').read_text(encoding='utf-8'))
 test=WORK/'all-variants-final';test.mkdir(exist_ok=True)
 for c in variants:
  source=ROOT/'variants'/f'variant-{c["variant"]:02}';dest=test/source.name;dest.mkdir(exist_ok=True)
  for path in source.iterdir():
   if path.is_file():shutil.copyfile(path,dest/path.name)
  c['port']=55474
  if c['incident']!='port':c['backup_port']=55474
  (dest/'config.json').write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding='utf-8')
 base=test/'variant-01'
 if not (base/'.local/cluster/PG_VERSION').exists():ps(base,'start')
 env=os.environ.copy();env['PGPASSFILE']=str(base/'.local/pgpass.conf');env['PGCLIENTENCODING']='UTF8'
 cluster=run([str(PGBIN/'psql.exe'),'-X','-w','-h','127.0.0.1','-p','55474','-U','postgres','-d','postgres','-Atc','SHOW data_directory'],env=env)
 assert Path(cluster).resolve()==(base/'.local/cluster').resolve(),'Refuse to reset any other cluster'
 results=[]
 for c in variants:
  folder=test/f'variant-{c["variant"]:02}'
  if c['variant']!=1:
   (folder/'.local').mkdir(exist_ok=True)
   shutil.copyfile(base/'.local/pgpass.conf',folder/'.local/pgpass.conf')
  for suffix in ['_restore','']:
   run([str(PGBIN/'dropdb.exe'),'-w','-h','127.0.0.1','-p','55474','-U','postgres','--if-exists','--force',c['database']+suffix],env=env)
  run([str(PGBIN/'psql.exe'),'-X','-w','-h','127.0.0.1','-p','55474','-U','postgres','-d','postgres','-v','ON_ERROR_STOP=1','-c',f'DROP ROLE IF EXISTS {c["database"]}_reader; DROP ROLE IF EXISTS {c["database"]}_restore_reader'],env=env)
  ps(folder,'seed')
  def sql(s,expected=0):return run([str(PGBIN/'psql.exe'),'-X','-w','-h','127.0.0.1','-p','55474','-U','postgres','-d',c['database'],'-v','ON_ERROR_STOP=1','-P','pager=off','-c',s],expected,env)
  before=ps(folder,'audit')
  role=c['database']+'_reader'
  case=c['incident']
  if case=='excess':
   assert ' t ' in before
   sql(f'REVOKE DELETE ON work.orders FROM {role}')
  elif case=='missing':
   sql(f'SET ROLE {role};SELECT count(*) FROM work.orders',1)
   sql(f'GRANT SELECT ON work.orders TO {role}')
  elif case=='index':
   assert 'Seq Scan' in before
   sql('CREATE INDEX orders_reference_idx ON work.orders(reference);ANALYZE work.orders')
  else:
   ps(folder,'backup',expected=1)
   c['backup_port']=c['port'];c['backup_dir']='backups'
   (folder/'config.json').write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding='utf-8')
  after=ps(folder,'audit')
  assert 'Index Scan' in after or 'Bitmap' in after
  denial=sql(f'BEGIN;SET LOCAL ROLE {role};DELETE FROM work.orders WHERE id=1;ROLLBACK',1)
  assert 'permission denied' in denial
  ps(folder,'backup')
  archive=max((folder/'backups').glob('*.dump'),key=lambda x:x.stat().st_mtime)
  size=archive.stat().st_size
  ps(folder,'restore','-Archive',str(archive))
  verify=ps(folder,'verify');assert verify.count('CONTROL ')==2
  negative=ps(folder,'backup','-Negative',expected=1)
  assert 'Requestednegativecheck' in ''.join(negative.split())
  # A modified dump must fail before creation of any new restore database.
  bad=folder/'backups/corrupt.dump';bad.write_bytes(archive.read_bytes()[:-20]+b'corrupt')
  shutil.copyfile(str(archive)+'.json',str(bad)+'.json')
  err=ps(folder,'restore','-Archive',str(bad),expected=1)
  assert 'SHA256mismatch' in ''.join(err.split())
  log=[json.loads(s) for s in (folder/'.local/operations.jsonl').read_text(encoding='utf-8-sig').splitlines()]
  assert log[-1]['status']=='FAIL'
  results.append(dict(variant=c['variant'],incident=case,rows=c['rows'],total=c['total'],digest=c['digest'],backup_bytes=size,permission_denied=True,restore_equal=True,failure_logged=True,corruption_rejected=True,before=before,after=after,verify=verify))
  (WORK/'runtime-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
  print('PASS',c['variant'],case,flush=True)
 (WORK/'runtime-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
 (WORK/'transcripts.json').write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf-8')
 print('All',len(results),'input sets passed')
if __name__=='__main__':
 try:main()
 finally:(WORK/'transcripts.json').write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf-8')
