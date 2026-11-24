#!/usr/bin/env bash
# The checks of the CI, here on this machine - the ONE entry point for the push guard (tools/hooks/pre-push) and for you:
#
#   tools/check_all.sh              style (ruff format + check) and every test, in parallel and gentle to the machine
#   CA_JOBS=2 tools/check_all.sh    fewer tests at the same time (a small / busy computer; default 3)
#
# A tree that has passed is remembered (.git/verified-tree): the same committed tree is not tested a second time (the push guard asks for the same
# check right after you ran it by hand). Needs a Python with the project's requirements plus pytest, pytest-xdist and ruff - by default the venv
# ~/.venvs/car-assistant (outside iCloud and outside the repository), or the one named in CA_VENV:
#   python3.12 -m venv ~/.venvs/car-assistant && ~/.venvs/car-assistant/bin/pip install -r carassistant/requirements.txt pytest pytest-xdist ruff httpx pyyaml
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
VENV=${CA_VENV:-$HOME/.venvs/car-assistant}
if [ ! -x "$VENV/bin/pytest" ]; then echo "check_all: no venv at $VENV (see the top of this file)"; exit 1; fi
export PYTHONDONTWRITEBYTECODE=1          # no .pyc files into the repository (a folder that iCloud or an indexer watches)
tree=$(git rev-parse 'HEAD^{tree}')
mark="$(git rev-parse --git-dir)/verified-tree"
clean=0; [ -z "$(git status --porcelain --untracked-files=no)" ] && clean=1
if [ "$clean" = 1 ] && [ -f "$mark" ] && [ "$(cat "$mark")" = "$tree" ]; then echo "check_all: this tree has passed already - nothing to do"; exit 0; fi
"$VENV/bin/ruff" format --check . >/dev/null || { echo "check_all: ruff format --check failed (run: $VENV/bin/ruff format .)"; exit 1; }
"$VENV/bin/ruff" check . >/dev/null || { echo "check_all: ruff check failed"; exit 1; }
nice -n 10 "$VENV/bin/pytest" -q -x -n "${CA_JOBS:-3}" -p no:cacheprovider
[ "$clean" = 1 ] && echo "$tree" > "$mark"
echo "check_all: all green"
