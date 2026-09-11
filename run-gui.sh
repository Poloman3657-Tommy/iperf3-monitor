#!/bin/sh
CDPATH= cd -P "$(dirname "$0")" || exit 2
if [ -x .venv/bin/python ]; then
    exec .venv/bin/python gui.py "$@"
fi
exec python3 gui.py "$@"
