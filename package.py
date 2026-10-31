"""Create a portable source ZIP from an explicit public allowlist."""
from pathlib import Path
import argparse,zipfile
FILES=['app.py','index.html','folder_picker.py','verify.py','verify_workflow.py','run.sh','package.py','README.md','ARCHITECTURE.md','.gitignore']
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('output');args=a.parse_args();root=Path(__file__).resolve().parent
 with zipfile.ZipFile(args.output,'x',zipfile.ZIP_DEFLATED) as z:
  for name in FILES:z.write(root/name,'imgvideo/'+name)
 print(args.output)
