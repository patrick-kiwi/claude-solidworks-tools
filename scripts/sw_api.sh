#!/usr/bin/env bash
# Look up SolidWorks API signatures / enum values offline (see sw_api.ps1 for the patterns).
#   sw_api.sh FeatureFillet*        sw_api.sh IFeatureManager.*Draft*   (several patterns: each in turn)
#   sw_api.sh -Enum '*FilletOptions*'      sw_api.sh -Enum '*' -Value EndCondBlind
set -euo pipefail
here="$(cd "$(dirname "$(realpath "${BASH_SOURCE[0]}")")" && pwd)"
ps1="$(wslpath -w "$here/sw_api.ps1")"
cd /mnt/c
# Several member patterns (no -Enum/-Value flags): look each one up in turn.
if [ $# -gt 1 ] && ! printf '%s\n' "$@" | grep -q '^-'; then
  for p in "$@"; do powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$ps1" "$p"; done
  exit 0
fi
exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$ps1" "$@"
