#!/usr/bin/env bash
# ============================================================
#  SpawnTools — Linux/macOS launcher
#
#  Make it executable once:  chmod +x spawntools.sh
#  Then run:                 ./spawntools.sh
#  • Finds Python 3.10+ automatically
#  • Installs Pillow + numpy on first run if they're missing
#  • Launches `python -m spawntools`
# ============================================================
set -u
cd "$(dirname "$0")"

# --- 1. Find a working Python 3.10+ ---
PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1; then
            PY="$candidate"
            break
        fi
    fi
done

if [ -z "$PY" ]; then
    cat <<'EOF'

============================================================
 Python 3.10 or newer is required but was not found.

 macOS:    brew install python@3.12
 Debian:   sudo apt install python3 python3-pip python3-tk
 Fedora:   sudo dnf install python3 python3-pip python3-tkinter
 Arch:     sudo pacman -S python python-pip tk
============================================================
EOF
    exit 1
fi

# --- 2. Verify tkinter is available (some Linux distros need it separately) ---
if ! "$PY" -c 'import tkinter' >/dev/null 2>&1; then
    cat <<EOF

============================================================
 tkinter is missing from your Python install.
 SpawnTools's GUI cannot start without it.

 Debian/Ubuntu:  sudo apt install python3-tk
 Fedora:         sudo dnf install python3-tkinter
 Arch:           sudo pacman -S tk
 macOS:          brew reinstall python-tk@3.12  (or matching version)
============================================================
EOF
    exit 1
fi

# --- 3. Ensure dependencies (Pillow + numpy) ---
if ! "$PY" -c 'import PIL, numpy' >/dev/null 2>&1; then
    echo "Installing dependencies on first run, please wait..."
    if ! "$PY" -m pip install --user -r requirements.txt; then
        echo
        echo "Dependency installation failed."
        echo "Try:  $PY -m pip install --user Pillow numpy"
        exit 1
    fi
fi

# --- 4. Launch the GUI ---
exec "$PY" -m spawntools
