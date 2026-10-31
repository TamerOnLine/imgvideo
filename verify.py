import tempfile,json,subprocess
from pathlib import Path
from app import tools,process_one,probe,digest,batch,STATE
T=tools();proof=[]
with tempfile.TemporaryDirectory(prefix="imgvideo-test-") as td:
 root=Path(td);src=root/'sources';out=root/'output';src.mkdir();out.mkdir()
 a=src/'اختبار صوت متعدد.mp4';b=src/'بلا صوت.mp4'
 cmd=[T['ffmpeg'],'-v','error','-f','lavfi','-i','color=c=blue:s=64x64:r=10:d=1','-f','lavfi','-i','sine=frequency=440:duration=1','-f','lavfi','-i','sine=frequency=880:duration=1','-map','0:v','-map','1:a','-map','2:a','-c:v','mpeg4','-c:a','aac',str(a)]
 subprocess.run(cmd,check=True);subprocess.run([T['ffmpeg'],'-v','error','-i',str(a),'-map','0:v','-c','copy',str(b)],check=True)
 originals={str(p):digest(p) for p in [a,b]}
 for p in [a,b]:
  r=process_one(p,out,T);assert r['audio_streams']==0;assert all(s['codec_type']=='video' for s in probe(Path(r['output']),T)['streams']);assert process_one(p,out,T)['state']=='resumed';proof.append({'case':p.name,'result':'passed','video_packet_hash':r['video_packet_hash']})
 r=process_one(a,out,T);target=Path(r['output']);target.write_bytes(b'collision')
 try:process_one(a,out,T);raise AssertionError('overwritten')
 except ValueError:assert target.read_bytes()==b'collision';proof.append({'case':'existing output collision','result':'passed'})
 bad=src/'broken.mp4';bad.write_bytes(b'not video')
 try:process_one(bad,out,T);raise AssertionError('invalid accepted')
 except ValueError:proof.append({'case':'invalid input rejected','result':'passed'})
 try:process_one(a,src,T);raise AssertionError('source folder accepted')
 except ValueError:proof.append({'case':'separate output enforced','result':'passed'})
 assert all(digest(Path(p))==h for p,h in originals.items());proof.append({'case':'original hashes unchanged','result':'passed'})
 # Same basename in different source folders remains traceable and distinct.
 other=root/'other';other.mkdir();copy=other/a.name;copy.write_bytes(a.read_bytes());new=process_one(copy,out,T);assert new['output']!=r['output'];proof.append({'case':'same basename different source','result':'passed'})
(root if False else STATE).joinpath('verification.json').write_text(json.dumps({'tools':T,'cases':proof,'synthetic_only':True,'limits':['No private videos or subjective quality review; incompatible stream-copy containers fail explicitly.']},ensure_ascii=False,indent=2))
print(json.dumps({'passed':len(proof),'proof':str(STATE/'verification.json')},ensure_ascii=False))
