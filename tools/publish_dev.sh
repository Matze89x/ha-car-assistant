#!/usr/bin/env bash
# Puts the folder carassistant-dev/ of the current dev branch onto main (and nothing else), so that Home Assistant's store - which reads the
# add-on list from main - offers the new Developer version. The released app on main stays as it is. Run after `git push origin dev`.
set -euo pipefail
cd "$(dirname "$0")/.."
version=$(sed -n 's/^version: "\(.*\)"/\1/p' carassistant-dev/config.yaml)
tmp=$(mktemp -d)
trap 'git worktree remove --force "$tmp" 2>/dev/null || true' EXIT
git fetch -q origin main
git worktree add -q --detach "$tmp" origin/main
rm -rf "$tmp/carassistant-dev"
cp -R carassistant-dev "$tmp/carassistant-dev"
cd "$tmp"
git add -A carassistant-dev
if git diff --cached --quiet; then echo "main already has Developer add-on $version"; exit 0; fi
git commit -q -m "Developer add-on $version

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push -q origin HEAD:main
echo "Developer add-on $version is on main"
