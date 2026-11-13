#!/usr/bin/env bash
# Look up SolidWorks API signatures / enum values offline (see sw_api.ps1 for the patterns).
#   sw_api.sh FeatureFillet*        sw_api.sh IFeatureManager.*Draft*
#   sw_api.sh -Enum '*FilletOptions*'      sw_api.sh -Enum '*' -Value EndCondBlind
set -euo pipefail
here="$(cd "$(dirname "$(realpath "${BASH_SOURCE[0]}")")" && pwd)"
ps1="$(wslpath -w "$here/sw_api.ps1")"
cd /mnt/c
exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$ps1" "$@"
