#!/bin/sh
# Install the Iskra WSGI pilot in the unpacked release directory.
set -eu
umask 077
cd "$(dirname "$0")"
python_bin="${PYTHON:-python3}"
"$python_bin" -c 'import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 12) else "Iskra requires Python 3.11 or 3.12")'
if [ ! -f .venv/pyvenv.cfg ]; then
    if [ -e .venv ]; then
        echo ".venv exists and is not a virtual environment" >&2
        exit 1
    fi
    "$python_bin" -m venv .venv
fi
.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
.venv/bin/python -m pip check
echo "Zainstalowano zależności Iskry. Konfiguracja i uruchomienie: docs/INSTALL_PILOT.md"
