#!/usr/bin/env sh
# One-time setup for propeller_studio (macOS / Linux / Git Bash).
#
#   sh propeller_studio/bootstrap.sh
set -e
here="$(cd "$(dirname "$0")" && pwd)"
root="$(dirname "$here")"
venv="$root/.venv-studio"

if [ -d "$venv/Scripts" ]; then py="$venv/Scripts/python.exe"; else py="$venv/bin/python"; fi
if [ ! -x "$py" ]; then
  echo "Creating $venv ..."
  python3 -m venv "$venv"
  if [ -d "$venv/Scripts" ]; then py="$venv/Scripts/python.exe"; else py="$venv/bin/python"; fi
fi
"$py" -m pip install --upgrade pip
"$py" -m pip install -r "$here/requirements.txt"

echo
echo "Installing the Node dependency for the FEG geometry backend ..."
( cd "$root" && npm install --no-audit --no-fund )

echo
echo "Done.  Try:"
echo "  $py -m propeller_studio gui"
