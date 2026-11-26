#!/usr/bin/env bash
# Waits for the CI run of ONE commit on GitHub and says how it ended; a failed run is shown with its failed tests (the annotations, which the public API
# serves without a login - the log itself needs one).
#
#   tools/ci_wait.sh [SHA] [REPO]        default: HEAD of this checkout, the repository of the `origin` remote
#
# The anonymous API of GitHub allows 60 requests an hour for ALL programs behind one internet address (the app reads its sources from raw.githubusercontent.com
# and no longer counts, but other add-ons and tools do). So this script asks rarely (first after 30 s, then every 60-90 s) and always with the ETag of the
# last answer: while nothing changed GitHub answers "not modified", and that costs no quota. It uses a token when there is one: an environment variable
# GITHUB_TOKEN or the file ~/.config/car-assistant/github-token. A token for PUBLIC data needs no rights at all (GitHub -> Settings -> Developer settings ->
# Fine-grained tokens -> "Public repositories (read-only)"); with it the limit is 5000 an hour. Never put the token into the repository or a chat.
#
# When the API limit is used up it reads the normal web page of the runs instead (green / red / running only).
# Exit code: 0 green, 1 red, 2 it could not be found out (no network).
set -u
cd "$(dirname "$0")/.." || exit 2
SHA=${1:-$(git rev-parse HEAD)}
REPO=${2:-$(git remote get-url origin | sed -E 's#.*[:/]([^/]+/[^/.]+)(\.git)?$#\1#')}
TOKEN=${GITHUB_TOKEN:-}
[ -z "$TOKEN" ] && [ -r "$HOME/.config/car-assistant/github-token" ] && TOKEN=$(tr -d '[:space:]' < "$HOME/.config/car-assistant/github-token")
cache=$(mktemp -d); trap 'rm -rf "$cache"' EXIT
api() {  # GET with the ETag of the last answer for this address: "304 not modified" is free
  local url=$1 key; key=$(printf '%s' "$url" | shasum | cut -c1-12)
  local args=(-s -D "$cache/$key.h" -o "$cache/$key.new")
  [ -n "$TOKEN" ] && args+=(-H "Authorization: Bearer $TOKEN")
  [ -s "$cache/$key.etag" ] && args+=(-H "If-None-Match: $(cat "$cache/$key.etag")")
  curl "${args[@]}" "$url"
  if head -1 "$cache/$key.h" | grep -q " 304"; then cat "$cache/$key.body"; return; fi
  mv "$cache/$key.new" "$cache/$key.body"
  grep -i '^etag:' "$cache/$key.h" | tr -d '\r' | sed -E 's/^[Ee][Tt][Aa][Gg]: //' > "$cache/$key.etag"
  cat "$cache/$key.body"
}

sleep 30  # a CI run needs a moment to start: no need to ask at once
wait_s=60
for _ in $(seq 1 60); do
  json=$(api "https://api.github.com/repos/$REPO/commits/$SHA/check-runs")
  verdict=$(printf '%s' "$json" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("RETRY no answer"); sys.exit()
msg = d.get("message", "")
if "rate limit" in msg.lower():
    print("LIMIT " + msg[:60]); sys.exit()
if "check_runs" not in d:
    print("RETRY " + msg[:60]); sys.exit()      # the commit is not there yet (the push is still on its way)
runs = d["check_runs"]
if not runs:
    print("RETRY no run yet")
elif any(r["status"] != "completed" for r in runs):
    print("RETRY running")
elif all(r["conclusion"] == "success" for r in runs):
    print("GREEN")
else:
    print("RED " + str(next(r["id"] for r in runs if r["conclusion"] != "success")))
')
  case "$verdict" in
    GREEN) echo "CI green for $SHA"; exit 0 ;;
    RED*)
      id=${verdict#RED }
      echo "CI RED for $SHA - failed tests:"
      api "https://api.github.com/repos/$REPO/check-runs/$id/annotations" | python3 -c '
import json, sys
for a in json.load(sys.stdin):
    t, m = a.get("title") or "", a.get("message") or ""
    if t.startswith("FAILED") or "exit code" not in m:
        print("  " + t); print("    " + m[:900].replace("\n", "\n    "))
'
      exit 1 ;;
    LIMIT*)  # the API limit is used up: the normal web page of the runs has no such limit and says green / red / running for the commit's title
      subject=$(git log -1 --format=%s "$SHA" 2>/dev/null | cut -c1-40)
      web=$(curl -s "https://github.com/$REPO/actions/workflows/ci.yml" | SUBJECT="$subject" python3 -c '
import html, os, re, sys
page, subject = sys.stdin.read(), os.environ["SUBJECT"]
for m in re.finditer(r"aria-label=\"((?:completed successfully|failed|in progress|queued|cancelled)[^\"]*)\"", page):
    label = html.unescape(m.group(1))
    if subject and subject in label:
        print("GREEN" if label.startswith("completed successfully") else "RED" if label.startswith(("failed", "cancelled")) else "RETRY running")
        break
else:
    print("RETRY not listed yet")
')
      case "$web" in
        GREEN) echo "CI green for $SHA (read from the web page: the API limit is used up)"; exit 0 ;;
        RED) echo "CI RED for $SHA (read from the web page) - open https://github.com/$REPO/actions for the failed tests, or try again when the API limit is back"; exit 1 ;;
      esac ;;
  esac
  sleep "$wait_s"; [ "$wait_s" -lt 90 ] && wait_s=$((wait_s + 10))
done
echo "gave up waiting for $SHA"; exit 2
