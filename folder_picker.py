"""Windows native folder picker. No uploads, account access or file changes."""
import base64, subprocess, threading, os
from pathlib import Path
_LOCK=threading.Lock()
SCRIPT=r"""Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$d = New-Object System.Windows.Forms.FolderBrowserDialog
$d.Description = 'imgvideo - Select video folder'
$d.ShowNewFolderButton = $false
try {
 if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
  [Console]::Write([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($d.SelectedPath)))
 }
} finally { $d.Dispose() }
"""
def convert(value):
 if len(value)>4096 or any(ord(c)<32 for c in value):raise ValueError('مسار المجلد غير صالح')
 if len(value)>2 and value[1:3] in (':\\',':/') and value[0].isascii() and value[0].isalpha():
  return '/mnt/'+value[0].lower()+'/'+value[3:].replace('\\','/')
 for prefix in ('\\\\wsl.localhost\\imgvideo\\','\\\\wsl$\\imgvideo\\'):
  if value.lower().startswith(prefix.lower()):return '/'+value[len(prefix):].replace('\\','/')
 raise ValueError('اختر مجلد قرص Windows أو مجلدًا داخل توزيعة imgvideo')
def choose():
 if not _LOCK.acquire(blocking=False):raise ValueError('نافذة اختيار المجلد مفتوحة بالفعل')
 try:
  exe='/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'
  if not Path(exe).is_file():raise ValueError('نافذة Windows غير متاحة؛ استخدم إدخال المسار')
  env=dict(os.environ)
  r=subprocess.run([exe,'-NoProfile','-STA','-EncodedCommand',base64.b64encode(SCRIPT.encode('utf-16le')).decode()],capture_output=True,timeout=180,env=env)
  if r.returncode:raise ValueError('تعذر فتح نافذة اختيار المجلد في Windows')
  raw=r.stdout.decode('utf-8-sig').strip()
  if not raw:return {'cancelled':True}
  value=base64.b64decode(raw,validate=True).decode('utf-8');local=Path(convert(value)).resolve(strict=True)
  if not local.is_dir():raise ValueError('المجلد المختار غير متاح داخل imgvideo')
  return {'cancelled':False,'path':str(local)}
 finally:_LOCK.release()
