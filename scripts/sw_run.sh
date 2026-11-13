#!/usr/bin/env bash
# Run a SolidWorks build script (which may live anywhere, including the WSL filesystem) under
# Windows Python, with swlib importable.   Usage: sw_run.sh path/to/script.py [args...]
#
# Windows Python is located once and cached in ~/.config/solidworks-skill/python
# (override with SW_PYTHON=/mnt/c/.../python.exe). It needs pywin32 installed.
set -euo pipefail

here="$(cd "$(dirname "$(realpath "${BASH_SOURCE[0]}")")" && pwd)"
cache="${XDG_CONFIG_HOME:-$HOME/.config}/solidworks-skill/python"

find_python() {
  local c
  for c in /mnt/c/Users/*/miniconda3/envs/*/python.exe /mnt/c/Users/*/anaconda3/envs/*/python.exe \
           /mnt/c/Users/*/miniconda3/python.exe /mnt/c/Users/*/anaconda3/python.exe \
           /mnt/c/Users/*/AppData/Local/Programs/Python/*/python.exe; do
    [ -x "$c" ] || continue
    (cd /mnt/c && "$c" -c "import win32com.client" >/dev/null 2>&1) && { echo "$c"; return 0; }
  done
  return 1
}

PY="${SW_PYTHON:-}"
if [ -z "$PY" ] && [ -f "$cache" ]; then PY="$(cat "$cache")"; fi
if [ -z "$PY" ] || [ ! -x "$PY" ]; then
  PY="$(find_python)" || { echo "No Windows Python with pywin32 found. Install one: pip install pywin32" >&2; exit 2; }
  mkdir -p "$(dirname "$cache")" && echo "$PY" > "$cache"
fi

[ $# -ge 1 ] || { echo "usage: $0 script.py [args...]" >&2; exit 2; }
script_win="$(wslpath -w "$(realpath "$1")")"
lib_win="$(wslpath -w "$here")"
shift
cd /mnt/c   # Windows exes complain when the cwd is a \\wsl$ path
# -u + reconfigure: stream output as it happens (builds take minutes) with Unix line endings.
exec "$PY" -u -c "import sys, runpy; [s.reconfigure(newline='\n', line_buffering=True) for s in (sys.stdout, sys.stderr)]; sys.path.insert(0, sys.argv[1]); sys.argv = sys.argv[2:]; runpy.run_path(sys.argv[0], run_name='__main__')" \
  "$lib_win" "$script_win" "$@"
