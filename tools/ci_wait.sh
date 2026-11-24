#!/usr/bin/env bash
# Waits for the CI run of ONE commit on GitHub and says how it ended; a failed run is shown with its failed tests (the annotations, which the public API
# serves without a login - the log itself needs one).
#
#   tools/ci_wait.sh [SHA] [REPO]        default: HEAD of this checkout, the repository of the `origin` remote
#
# The anonymous API of GitHub allows 60 requests an hour for ALL programs behind one internet address (the app's own checks of its sources count too).
# So this script asks rarely (every 45 s, and a bit more often at the start), and it uses a token when there is one: an environment variable
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
api() { if [ -n "$TOKEN" ]; then curl -s -H "Authorization: Bearer $TOKEN" "$1"; else curl -s "$1"; fi; }

wait_s=20
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
  sleep "$wait_s"; [ "$wait_s" -lt 45 ] && wait_s=$((wait_s + 5))
done
echo "gave up waiting for $SHA"; exit 2
