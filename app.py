import argparse, fcntl, hashlib, json, os, secrets, shutil, subprocess, threading, time, uuid
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
ROOT=Path(__file__).resolve().parent
STATE=ROOT/'state'; STATE.mkdir(exist_ok=True)
TOKEN=secrets.token_urlsafe(32)
STATUS={'running':False,'items':[]}
LOCK=threading.Lock()
EXT={'.mp4','.mkv','.mov','.avi','.webm','.m4v','.ts','.mts'}

def local_path(value, must_exist=True):
 if not isinstance(value,str) or not value.strip():raise ValueError('أدخل مسار المجلد')
 value=value.strip().strip('"')
 if len(value)>4096 or any(ord(c)<32 for c in value):raise ValueError('مسار غير صالح')
 if len(value)>2 and value[1]==':' and value[0].isascii() and value[0].isalpha():value='/mnt/'+value[0].lower()+'/'+value[2:].lstrip('\\/').replace('\\','/')
 for prefix in ('\\\\wsl.localhost\\imgvideo\\','\\\\wsl$\\imgvideo\\'):
  if value.lower().startswith(prefix.lower()):value='/'+value[len(prefix):].replace('\\','/')
 if not value.startswith('/') or value.startswith('//'):raise ValueError('أدخل مسار Windows كاملًا أو مسار WSL')
 path=Path(value).resolve()
 if must_exist and not path.exists():
  parts=path.parts
  if len(parts)>2 and parts[1]=='mnt' and len(parts[2])==1 and not Path('/mnt',parts[2]).is_dir():raise ValueError('القرص '+parts[2].upper()+': غير متاح داخل WSL؛ اختر قرصًا متاحًا. لم نغير ربط الأقراص.')
  raise ValueError('المجلد أو الملف غير موجود أو غير متاح داخل WSL: '+str(path))
 return path

def prepare_batch(files, output, create=False):
 if not isinstance(files,list) or not 1<=len(files)<=10000 or any(not isinstance(x,str) for x in files):raise ValueError('اعرض الملفات وحدد فيديو واحدًا على الأقل')
 paths=list(dict.fromkeys(str(local_path(x)) for x in files));out=local_path(output,False)
 for value in paths:
  p=Path(value)
  if not p.is_file() or p.suffix.lower() not in EXT:raise ValueError('ملف غير مدعوم: '+p.name)
  if out==p.parent or out in p.parents:raise ValueError('مجلد الإخراج مطابق للمصدر أو أحد مجلداته الأعلى؛ اختر مجلدًا منفصلًا أو استخدم الاقتراح')
 if out.exists() and not out.is_dir():raise ValueError('مسار الإخراج ليس مجلدًا')
 if not out.exists():
  if not create:raise ValueError('مجلد الإخراج غير موجود؛ فعّل إنشاء مجلد الإخراج أو اختر مجلدًا موجودًا')
  if not out.parent.is_dir():raise ValueError('المجلد الأب للإخراج غير موجود؛ اختر مسارًا متاحًا')
  out.mkdir()
 return paths,str(out)

def digest(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def atomic(p,d):
 t=p.with_name(p.name+'.'+uuid.uuid4().hex+'.tmp')
 with open(t,'x') as f:json.dump(d,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(t,p)
def tools(settings=None):
 settings=settings or {}
 result={}
 for name in ('ffmpeg','ffprobe'):
  value=settings.get(name) or shutil.which(name)
  if not value:raise ValueError('لم يُعثر على '+name+'؛ ثبّته أو حدد مساره في الإعدادات')
  p=Path(value).resolve(strict=True)
  if not p.is_file() or not os.access(p,os.X_OK):raise ValueError('مسار الأداة غير قابل للتنفيذ')
  r=subprocess.run([str(p),'-version'],capture_output=True,text=True,timeout=10,check=True)
  if not r.stdout.startswith(name+' version'):raise ValueError('الملف ليس الأداة المحددة')
  result[name]=str(p);result[name+'_version']=r.stdout.splitlines()[0]
 return result
def run(args):
 r=subprocess.run(args,capture_output=True,text=True,timeout=7200)
 if r.returncode:raise ValueError(r.stderr[-2000:] or 'فشل أمر الفيديو')
 return r.stdout
def probe(p,t):return json.loads(run([t['ffprobe'],'-v','error','-show_streams','-show_format','-of','json',str(p)]))
def video_hash(p,t):return run([t['ffmpeg'],'-v','error','-i',str(p),'-map','0:v','-c','copy','-f','streamhash','-hash','sha256','-']).strip()
def process_one(source,output,t):
 source=Path(source).resolve(strict=True);output=Path(output).resolve(strict=True)
 if not source.is_file() or source.suffix.lower() not in EXT:raise ValueError('اختر ملف فيديو مدعومًا')
 if source.parent==output or output in source.parents:raise ValueError('اختر مجلد إخراج منفصلًا عن مجلد المصادر')
 before=digest(source);identity=hashlib.sha256((str(source)+'\0'+before).encode()).hexdigest()[:20]
 target=output/(source.stem+'--silent-'+identity+'.mkv');record=output/('.imgvideo-'+identity+'.json')
 if record.exists():
  old=json.loads(record.read_text())
  if old.get('state')=='complete' and target.is_file() and digest(target)==old.get('output_sha256') and old.get('source_sha256')==before:
   return {'source':str(source),'output':str(target),'state':'resumed','verified':True}
 if target.exists():raise ValueError('النتيجة موجودة؛ لن تُستبدل دون دليل اكتمال مطابق')
 info=probe(source,t);videos=[s for s in info['streams'] if s['codec_type']=='video']
 if not videos:raise ValueError('الملف لا يحتوي مسار فيديو')
 temp=output/('.imgvideo-partial-'+uuid.uuid4().hex+'.mkv')
 atomic(record,{'state':'processing','source':str(source),'source_sha256':before,'output':str(target),'partial':str(temp)})
 try:
  run([t['ffmpeg'],'-nostdin','-v','error','-n','-i',str(source),'-map','0:v','-c:v','copy','-an','-sn','-dn','-map_metadata','-1','-map_chapters','-1','-f','matroska',str(temp)])
  after=probe(temp,t);streams=after['streams']
  if len(streams)!=len(videos) or any(s['codec_type']!='video' for s in streams):raise ValueError('فشل عزل المسارات في النتيجة')
  if [s['codec_name'] for s in streams]!=[s['codec_name'] for s in videos]:raise ValueError('تغير ترميز الفيديو')
  a=video_hash(source,t);b=video_hash(temp,t)
  if a!=b:raise ValueError('بصمة حزم الفيديو غير مطابقة؛ لم تعتمد النتيجة')
  run([t['ffmpeg'],'-nostdin','-v','error','-i',str(temp),'-map','0:v','-f','null','-'])
  if digest(source)!=before:raise ValueError('تغير الأصل أثناء المعالجة؛ لم تعتمد النتيجة')
  # hard-link is atomic and refuses an existing target; no overwrite race.
  os.link(temp,target);temp.unlink()
  result={'state':'complete','source':str(source),'source_sha256':before,'output':str(target),'output_sha256':digest(target),'video_packet_hash':a,'audio_streams':0,'video_codecs':[s['codec_name'] for s in streams],'verified':True}
  atomic(record,result);return result
 except Exception as e:
  atomic(record,{'state':'failed','source':str(source),'source_sha256':before,'partial':str(temp),'error':str(e)})
  raise

def settings():
 p=STATE/'tools.json'
 return json.loads(p.read_text()) if p.exists() else {}
def batch(files,output):
 global STATUS
 try:
  t=tools(settings());out=Path(output).resolve(strict=True)
  if not out.is_dir():raise ValueError('مجلد الإخراج غير موجود')
  with open(out/'.imgvideo.lock','a+') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
   for i,source in enumerate(files):
    STATUS['current']=str(source);STATUS['position']=i+1
    try:r=process_one(source,out,t)
    except Exception as e:r={'source':source,'state':'failed','error':str(e)}
    STATUS['items'].append(r);atomic(STATE/'last-batch.json',STATUS)
 except Exception as e:STATUS['error']=str(e)
 finally:STATUS['running']=False;atomic(STATE/'last-batch.json',STATUS)
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def reply(self,code,value,ctype='application/json; charset=utf-8'):
  data=value.encode() if isinstance(value,str) else json.dumps(value,ensure_ascii=False).encode()
  self.send_response(code);self.send_header('Content-Type',ctype);self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
 def do_GET(self):
  try:
   if (self.headers.get('Host') or '').split(':')[0] not in ('localhost','127.0.0.1'):return self.reply(403,{'error':'Local host required'})
   u=urlparse(self.path)
   if u.path=='/':return self.reply(200,(ROOT/'index.html').read_text().replace('__TOKEN__',TOKEN),'text/html; charset=utf-8')
   if u.path=='/api/status':return self.reply(200,STATUS)
   if u.path=='/api/tools':
    try:return self.reply(200,{'ok':True,**tools(settings())})
    except Exception as e:return self.reply(200,{'ok':False,'error':str(e)})
   if u.path=='/api/browse':
    p=local_path(parse_qs(u.query).get('directory',['/mnt'])[0])
    return self.reply(200,{'directory':str(p),'parent':str(p.parent),'directories':[{'name':x.name,'path':str(x)} for x in sorted(p.iterdir()) if x.is_dir() and not x.name.startswith('.')]})
   if u.path=='/api/files':
    p=local_path(parse_qs(u.query).get('directory',[''])[0])
    if not p.is_dir():raise ValueError('المجلد غير موجود')
    return self.reply(200,{'directory':str(p),'suggested_output':str(p.parent/(p.name+'-silent')),'files':[str(x) for x in sorted(p.iterdir()) if x.is_file() and x.suffix.lower() in EXT]})
   return self.reply(404,{'error':'Not found'})
  except Exception as e:return self.reply(400,{'error':str(e)})
 def do_POST(self):
  global STATUS
  try:
   if (self.headers.get('Host') or '').split(':')[0] not in ('localhost','127.0.0.1'):return self.reply(403,{'error':'Local host required'})
   if self.headers.get('X-Imgvideo-Token')!=TOKEN:return self.reply(403,{'error':'أعد تحميل الصفحة'})
   size=int(self.headers.get('Content-Length','0'))
   if size>1024*1024:raise ValueError('طلب أكبر من الحد')
   d=json.loads(self.rfile.read(size))
   if self.path=='/api/choose-folder':
    from folder_picker import choose
    return self.reply(200,choose())
   if self.path=='/api/settings':
    checked=tools(d);atomic(STATE/'tools.json',{k:checked[k] for k in ('ffmpeg','ffprobe')});return self.reply(200,{'ok':True})
   if self.path=='/api/start':
    tools(settings())
    files,output=prepare_batch(d.get('files'),d.get('output'),d.get('create_output') is True)
    with LOCK:
     if STATUS['running']:raise ValueError('دفعة قيد العمل بالفعل')
     STATUS={'running':True,'items':[],'total':len(files),'position':0}
     threading.Thread(target=batch,args=(files,output),daemon=True).start()
    return self.reply(202,{'ok':True})
   return self.reply(404,{'error':'Not found'})
  except Exception as e:return self.reply(400,{'error':str(e)})
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--port',type=int,default=42120);args=a.parse_args();ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
