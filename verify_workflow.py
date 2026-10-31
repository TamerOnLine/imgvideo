"""Synthetic acceptance; never reads owner videos/settings."""
import json,tempfile,threading,time,urllib.request,urllib.error,subprocess
from pathlib import Path
import app
op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with tempfile.TemporaryDirectory(prefix='imgvideo-workflow-') as td:
 root=Path(td);app.STATE=root/'state';app.STATE.mkdir();app.STATUS={'running':False,'items':[]}
 src=root/'input';src.mkdir();video=src/'اختبار مسار.mp4';out=root/'output'
 subprocess.run([app.tools()['ffmpeg'],'-v','error','-f','lavfi','-i','color=c=red:s=64x64:r=10:d=1','-f','lavfi','-i','sine=duration=1','-c:v','mpeg4','-c:a','aac','-shortest',str(video)],check=True)
 original=app.digest(video)
 server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
 base='http://127.0.0.1:'+str(server.server_port)
 def request(path,data=None):
  req=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json','X-Imgvideo-Token':app.TOKEN})
  with op.open(req,timeout=10) as r:return json.loads(r.read())
 try:
  request('/api/workflow',{'directory':str(src),'output':str(out),'create_output':True});saved=request('/api/workflow');assert saved['output']==str(out) and not out.exists()
  app.STATUS['running']=True
  try:request('/api/start',{'files':[str(video)],'output':str(out),'create_output':True});raise AssertionError('busy accepted')
  except urllib.error.HTTPError as e:assert e.code==400 and not out.exists()
  app.STATUS['running']=False
  request('/api/start',{'files':[str(video)],'output':str(out),'create_output':True})
  deadline=time.time()+30
  while app.STATUS['running'] and time.time()<deadline:time.sleep(.05)
  assert not app.STATUS['running'] and app.STATUS['items'][0]['state']=='complete'
  result=Path(app.STATUS['items'][0]['output']);digest=app.digest(result);mtime=result.stat().st_mtime_ns
  app.atomic(app.STATE/'last-batch.json',{**app.STATUS,'running':True})
  app.STATUS=app.restored_status(app.STATE);assert app.STATUS['interrupted'] and not app.STATUS['running']
  assert request('/api/status')['can_resume']
  request('/api/resume',{})
  deadline=time.time()+30
  while app.STATUS['running'] and time.time()<deadline:time.sleep(.05)
  assert not app.STATUS['running'] and app.STATUS['items'][0]['state']=='resumed'
  assert app.digest(result)==digest and result.stat().st_mtime_ns==mtime and app.digest(video)==original
  with op.open(base+'/api/download?output='+app.quote(str(result)),timeout=10) as r:
   import hashlib
   assert hashlib.sha256(r.read()).hexdigest()==digest and 'attachment' in r.headers['Content-Disposition']
  try:request('/api/download?output=/etc/passwd');raise AssertionError('private path accepted')
  except urllib.error.HTTPError as e:assert e.code==404
  print(json.dumps({'passed':['settings persist without processing','busy start does not create output','synthetic processing','interrupted status','explicit resume skips verified output without rewrite','download bytes','unlisted download rejected','original unchanged'],'synthetic_only':True}))
 finally:server.shutdown();server.server_close()
