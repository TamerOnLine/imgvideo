#!/bin/sh
set -eu
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "Python 3 is required" >&2; exit 1; }
python3 -c 'import fcntl' || { echo "Run inside Linux or WSL; native Windows is unsupported" >&2; exit 1; }
echo 'Open http://localhost:42120/ after startup. Stop with Ctrl+C after the batch finishes.'
exec python3 app.py --port 42120
