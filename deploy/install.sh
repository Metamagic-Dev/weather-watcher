#!/usr/bin/env bash
# Installs the launchd service(s) that keep the download site running on
# this Mac. Run this once, from a checkout of this repo, after completing
# the manual cloudflared setup steps in the README ("Local download site"
# section) -- this script only wires up the *services*, it doesn't create
# a tunnel or its DNS route.
#
# Usage:
#   ./deploy/install.sh                 # fresh setup: web server + a new cloudflared tunnel service
#   ./deploy/install.sh --web-only      # you already run cloudflared for other hostnames on this
#                                        # Mac -- installs only the web server, and you add this
#                                        # site's hostname as another ingress rule in your existing
#                                        # ~/.cloudflared/config.yml instead (see README)
#
# Env vars:
#   SPC_STORY_OUTPUT_DIR   Folder the web server serves (default: ~/spc-outlook-site/stories).
#                          Must match what spc_story_generator.py writes to.
#   SPC_STORY_WEB_PORT     Local port for the web server (default: 8787). Change this if that
#                          port's already taken by something else on the Mac (e.g. another
#                          service proxied through the same existing tunnel) -- and update your
#                          ~/.cloudflared/config.yml ingress rule to match.
set -euo pipefail

WEB_ONLY=false
for arg in "$@"; do
  case "$arg" in
    --web-only) WEB_ONLY=true ;;
    *)
      echo "Unknown argument: $arg (supported: --web-only)" >&2
      exit 1
      ;;
  esac
done

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SITE_DIR="${SPC_STORY_OUTPUT_DIR:-$HOME/spc-outlook-site/stories}"
PORT="${SPC_STORY_WEB_PORT:-8787}"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

PYTHON3="$(command -v python3)"

mkdir -p "$LAUNCH_AGENTS" "$REPO_DIR/deploy/logs" "$SITE_DIR"

render() {
  sed \
    -e "s#__REPO_DIR__#$REPO_DIR#g" \
    -e "s#__SITE_DIR__#$SITE_DIR#g" \
    -e "s#__PORT__#$PORT#g" \
    -e "s#__PYTHON3__#$PYTHON3#g" \
    -e "s#__CLOUDFLARED__#${CLOUDFLARED:-}#g" \
    "$1"
}

render "$REPO_DIR/deploy/com.metamagicdev.spc-outlook-web.plist.template" \
  > "$LAUNCH_AGENTS/com.metamagicdev.spc-outlook-web.plist"

labels=(com.metamagicdev.spc-outlook-web)

if [ "$WEB_ONLY" = false ]; then
  CLOUDFLARED="$(command -v cloudflared || true)"
  if [ -z "$CLOUDFLARED" ]; then
    echo "cloudflared not found on PATH -- install it first (e.g. 'brew install cloudflared')." >&2
    exit 1
  fi
  render "$REPO_DIR/deploy/com.metamagicdev.spc-outlook-tunnel.plist.template" \
    > "$LAUNCH_AGENTS/com.metamagicdev.spc-outlook-tunnel.plist"
  labels+=(com.metamagicdev.spc-outlook-tunnel)
fi

for label in "${labels[@]}"; do
  launchctl unload "$LAUNCH_AGENTS/$label.plist" 2>/dev/null || true
  launchctl load "$LAUNCH_AGENTS/$label.plist"
done

echo "Installed and started:"
echo "  - com.metamagicdev.spc-outlook-web    (serves $SITE_DIR on http://127.0.0.1:$PORT)"
if [ "$WEB_ONLY" = false ]; then
  echo "  - com.metamagicdev.spc-outlook-tunnel (cloudflared tunnel run spc-outlook)"
else
  echo "  - (--web-only: no new tunnel service installed -- make sure your existing"
  echo "     cloudflared config routes a hostname to http://127.0.0.1:$PORT and has"
  echo "     been restarted to pick up that change)"
fi
echo
echo "Logs: $REPO_DIR/deploy/logs/"
echo "Make sure spc_story_generator.py writes to the same directory: export SPC_STORY_OUTPUT_DIR=$SITE_DIR"
