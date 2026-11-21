#!/usr/bin/env bash
# Update to the latest version, install packages and start Drone Map.
cd "$(dirname "$0")" || exit 1
PY=python3; command -v python3 >/dev/null 2>&1 || PY=python
if command -v git >/dev/null 2>&1 && [ -d .git ]; then
  echo "Updating Drone Map..."
  git fetch -q origin && { git checkout -q main 2>/dev/null || git checkout -q -b main origin/main; } \
    && git pull -q --ff-only origin main || echo "Could not update automatically, starting the version you have."
fi
echo "Checking packages..."
"$PY" -m pip install -q --disable-pip-version-check -r requirements.txt || exit 1
exec "$PY" run.py "$@"
