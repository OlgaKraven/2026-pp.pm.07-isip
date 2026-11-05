param(
 [Parameter(Mandatory=$true)][ValidateSet('start','seed','health','audit','repair','backup','restore','verify','schedule','task-status','task-remove','stop')][string]$Action,
 [string]$PgBin='C:\Program Files\PostgreSQL\18\bin',
 [string]$Archive,
 [switch]$Negative,
 [switch]$OneTime
)
$ErrorActionPreference='Stop'
$env:PSModulePath="$env:ProgramFiles\WindowsPowerShell\Modules;$PSHOME\Modules"
Import-Module "$PSHOME\Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1" -Force
$root=$PSScriptRoot
$cfg=Get-Content -LiteralPath (Join-Path $root 'config.json') -Raw | ConvertFrom-Json
$local=Join-Path $root '.local'
$data=Join-Path $local 'cluster'
$env:PGPASSFILE=Join-Path $local 'pgpass.conf'
$env:PGCLIENTENCODING='UTF8'
$env:PGCONNECT_TIMEOUT='5'
$hostPort=[int]$cfg.port
$db=[string]$cfg.database
if($db -notmatch '^pp07_v\d{2}$'){throw 'database must be pp07_vNN'}
if($hostPort -lt 55000 -or $hostPort -gt 55999){throw 'Use a dedicated port 55000..55999'}
$bin=Resolve-Path -LiteralPath $PgBin
function Native([string]$exe,[string[]]$argv){
 & (Join-Path $bin $exe) @argv
 if($LASTEXITCODE -ne 0){throw "$exe failed: $LASTEXITCODE"}
}
function Sql([string]$text,[string]$target=$db){
 Native 'psql.exe' @('-X','-w','-h','127.0.0.1','-p',"$hostPort",'-U','postgres','-d',$target,'-v','ON_ERROR_STOP=1','-P','pager=off','-c',$text)
}
function CheckExpected([string]$target){
 $value=& (Join-Path $bin 'psql.exe') -X -w -h 127.0.0.1 -p $hostPort -U postgres -d $target -v ON_ERROR_STOP=1 -Atc "SELECT count(*)::text||'|'||sum(amount)::text||'|'||md5(string_agg(id||'|'||reference||'|'||amount||'|'||status,E'\n' ORDER BY id)) FROM work.orders"
 if($LASTEXITCODE -ne 0){throw 'Control query failed'}
 $wanted="$($cfg.rows)|$($cfg.total)|$($cfg.digest)"
 if($value.Trim() -ne $wanted){throw "Mismatch: expected $wanted actual $value"}
 Write-Output "CONTROL $target $value OK"
}
switch($Action){
 'start'{
  if(Test-Path -LiteralPath $data){throw 'Cluster already exists. Preserve it; use health or pg_ctl status.'}
  New-Item -ItemType Directory -Force -Path $local | Out-Null
  $secret=[guid]::NewGuid().ToString('N')+[guid]::NewGuid().ToString('N')
  $passwordFile=Join-Path $local 'init-password.txt'
  [IO.File]::WriteAllText($passwordFile,$secret,[Text.UTF8Encoding]::new($false))
  [IO.File]::WriteAllText($env:PGPASSFILE,"127.0.0.1:$hostPort`:*:postgres:$secret`n",[Text.UTF8Encoding]::new($false))
  $me=[Security.Principal.WindowsIdentity]::GetCurrent().Name
  & icacls.exe $local /inheritance:r /grant:r "${me}:(OI)(CI)F" | Out-Null
  if($LASTEXITCODE -ne 0){throw 'Cannot restrict local credentials directory'}
  try{ Native 'initdb.exe' @('-D',$data,'-U','postgres','--auth=scram-sha-256','--encoding=UTF8','--locale=C',"--pwfile=$passwordFile") }
  finally{Remove-Item -LiteralPath $passwordFile -Force}
  Add-Content -LiteralPath (Join-Path $data 'postgresql.conf') -Encoding UTF8 -Value "`nlisten_addresses='127.0.0.1'`nport=$hostPort`nshared_buffers='64MB'`nmax_connections=20`nlog_connections=on`nlog_disconnections=on`n"
  Native 'pg_ctl.exe' @('-D',$data,'-l',(Join-Path $local 'server.log'),'-w','start')
  Write-Output "SERVER 127.0.0.1:$hostPort ready; SCRAM; private credentials in .local"
 }
 'seed'{
  Native 'createdb.exe' @('-w','-h','127.0.0.1','-p',"$hostPort",'-U','postgres',$db)
  Sql 'CREATE SCHEMA work; CREATE TABLE work.orders(id integer PRIMARY KEY, reference text NOT NULL, amount numeric(12,2) NOT NULL CHECK(amount>=0), status text NOT NULL);'
  $csv=(Join-Path $root 'orders.csv').Replace('\','/')
  Native 'psql.exe' @('-X','-w','-h','127.0.0.1','-p',"$hostPort",'-U','postgres','-d',$db,'-v','ON_ERROR_STOP=1','-c',"\copy work.orders FROM '$csv' WITH (FORMAT csv,HEADER true)")
  $role="${db}_reader"
  Sql "CREATE ROLE $role NOLOGIN; GRANT CONNECT ON DATABASE $db TO $role; GRANT USAGE ON SCHEMA work TO $role; GRANT SELECT ON work.orders TO $role;"
  Sql 'CREATE INDEX orders_reference_idx ON work.orders(reference)'
  Sql 'ANALYZE work.orders'
  if($cfg.incident -eq 'excess'){Sql "GRANT DELETE ON work.orders TO $role"}
  if($cfg.incident -eq 'missing'){Sql "REVOKE SELECT ON work.orders FROM $role"}
  if($cfg.incident -eq 'index'){Sql 'DROP INDEX work.orders_reference_idx'}
  CheckExpected $db
 }
 'health'{
  Native 'pg_ctl.exe' @('-D',$data,'status')
  Native 'pg_isready.exe' @('-h','127.0.0.1','-p',"$hostPort")
  Sql "SELECT version(); SELECT current_database(),inet_server_addr(),inet_server_port(),pg_database_size(current_database()); SHOW listen_addresses; SHOW password_encryption; SELECT name,setting FROM pg_settings WHERE name IN ('max_connections','shared_buffers'); SELECT pid,state,wait_event_type FROM pg_stat_activity WHERE datname=current_database(); SELECT rule_number,type,address,auth_method,error FROM pg_hba_file_rules;"
  CheckExpected $db
 }
 'audit'{
  $role="${db}_reader"
  Sql "SELECT '$role' AS role,has_table_privilege('$role','work.orders','SELECT') AS can_read,has_table_privilege('$role','work.orders','DELETE') AS can_delete; SELECT indexname FROM pg_indexes WHERE schemaname='work'; EXPLAIN (ANALYZE,BUFFERS) SELECT * FROM work.orders WHERE reference='REF-000777';"
  Write-Output "BACKUP PORT $($cfg.backup_port); SERVER PORT $hostPort"
  Write-Output "BACKUP TARGET $($cfg.backup_dir)"
 }
 'repair'{
  throw 'Use the explicit SQL or edit config.json described for the assigned incident. No automatic repair.'
 }
 'backup'{
  $begin=Get-Date
  $out=Join-Path $root $cfg.backup_dir
  $log=Join-Path $local 'operations.jsonl'
  $dumpFile=$null
  try{
   if($Negative){throw 'Requested negative check: no successful archive should appear'}
   New-Item -ItemType Directory -Force -Path $out | Out-Null
   $stamp=Get-Date -Format 'yyyyMMdd-HHmmss-fff'
   $dumpFile=Join-Path $out "$db-$stamp.dump"
   Native 'pg_dump.exe' @('-w','-h','127.0.0.1','-p',"$($cfg.backup_port)",'-U','postgres','-d',$db,'-Fc','--no-owner','--no-privileges','-f',"$dumpFile.partial")
   Native 'pg_restore.exe' @('--list',"$dumpFile.partial") | Out-Null
   Move-Item -LiteralPath "$dumpFile.partial" -Destination $dumpFile
   $hash=(Get-FileHash -LiteralPath $dumpFile -Algorithm SHA256).Hash.ToLowerInvariant()
   [ordered]@{database=$db;file=(Split-Path $dumpFile -Leaf);sha256=$hash;rows=$cfg.rows;total=$cfg.total;created=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath "$dumpFile.json" -Encoding UTF8
   [ordered]@{time=(Get-Date).ToString('o');action='backup';status='OK';database=$db;file=$dumpFile;seconds=[math]::Round(((Get-Date)-$begin).TotalSeconds,3)} | ConvertTo-Json -Compress | Add-Content -LiteralPath $log -Encoding UTF8
   Write-Output "BACKUP OK $dumpFile SHA256 $hash"
  }catch{
   [ordered]@{time=(Get-Date).ToString('o');action='backup';status='FAIL';database=$db;error=$_.Exception.Message} | ConvertTo-Json -Compress | Add-Content -LiteralPath $log -Encoding UTF8
   Write-Error $_ -ErrorAction Continue
   exit 1
  }
 }
 'restore'{
  if(-not $Archive){throw 'Pass -Archive with a specific checked dump'}
  $archivePath=(Resolve-Path -LiteralPath $Archive).Path
  $meta=Get-Content -LiteralPath "$archivePath.json" -Raw | ConvertFrom-Json
  if($meta.database -ne $db){throw 'Archive belongs to another variant'}
  $hash=(Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
  if($hash -ne $meta.sha256){throw 'SHA256 mismatch: do not restore this archive'}
  Native 'pg_restore.exe' @('--list',$archivePath) | Out-Null
  $target="${db}_restore"
  Native 'createdb.exe' @('-w','-h','127.0.0.1','-p',"$hostPort",'-U','postgres',$target)
  $begin=Get-Date
  Native 'pg_restore.exe' @('-w','-h','127.0.0.1','-p',"$hostPort",'-U','postgres','-d',$target,'--exit-on-error','--single-transaction','--no-owner','--no-privileges',$archivePath)
  CheckExpected $target
  Sql "CREATE ROLE ${db}_restore_reader NOLOGIN; GRANT CONNECT ON DATABASE $target TO ${db}_restore_reader; GRANT USAGE ON SCHEMA work TO ${db}_restore_reader; GRANT SELECT ON work.orders TO ${db}_restore_reader;" $target
  $seconds=[math]::Round(((Get-Date)-$begin).TotalSeconds,3)
  Write-Output "RESTORE OK $target seconds=$seconds; target limit $($cfg.rto_seconds) seconds"
  if($seconds -gt $cfg.rto_seconds){throw 'RTO exceeded: record the measured result, do not mark it passed'}
 }
 'verify'{
  CheckExpected $db;CheckExpected "${db}_restore"
  Sql "SELECT has_table_privilege('${db}_reader','work.orders','SELECT') AS can_read,has_table_privilege('${db}_reader','work.orders','DELETE') AS can_delete; SET ROLE ${db}_reader; SELECT count(*) FROM work.orders; RESET ROLE;"
  Sql "SELECT has_table_privilege('${db}_restore_reader','work.orders','SELECT') AS can_read,has_table_privilege('${db}_restore_reader','work.orders','DELETE') AS can_delete" "${db}_restore"
 }
 'schedule'{
  $taskName="PP07-$db"
  if(Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue){throw 'Task already exists. Review it; do not overwrite silently.'}
  $scriptPath=Join-Path $root 'lab.ps1'
  $arguments='-NoProfile -NonInteractive -File "'+$scriptPath+'" -Action backup -PgBin "'+$bin+'"'
  $act=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments -WorkingDirectory $root
  $trigger=if($OneTime){New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1)}else{New-ScheduledTaskTrigger -Daily -At $cfg.backup_time}
  $me=[Security.Principal.WindowsIdentity]::GetCurrent().Name
  $principal=New-ScheduledTaskPrincipal -UserId $me -LogonType Interactive -RunLevel Limited
  $settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
  Register-ScheduledTask -TaskName $taskName -Action $act -Trigger $trigger -Principal $principal -Settings $settings -Description "PP07 isolated lab $db" | Select-Object TaskName,State
  Write-Output 'Task runs only while this Windows user is logged in. Verify the trigger automatically, then disable/remove the training task after evidence is saved.'
 }
 'task-status'{
  Get-ScheduledTask -TaskName "PP07-$db" | Format-List TaskName,State,Triggers,Actions
  Get-ScheduledTaskInfo -TaskName "PP07-$db" | Format-List LastRunTime,LastTaskResult,NextRunTime
  if(Test-Path -LiteralPath (Join-Path $local 'operations.jsonl')){Get-Content -LiteralPath (Join-Path $local 'operations.jsonl') -Tail 3}
 }
 'task-remove'{
  Unregister-ScheduledTask -TaskName "PP07-$db" -Confirm:$false
  Write-Output "Removed only training task PP07-$db"
 }
 'stop'{Native 'pg_ctl.exe' @('-D',$data,'-m','fast','-w','stop')}
}
