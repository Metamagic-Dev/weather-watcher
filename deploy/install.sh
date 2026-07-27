#!/usr/bin/env bash
# Installs the two launchd services (local web server + Cloudflare Tunnel)
# that keep the download site running on this Mac. Run this once, from a
# checkout of this repo, after completing the manual cloudflared setup
# steps in the README ("Local download site" section) -- this script only
# wires up the *services*, it doesn't create the tunnel or its DNS route.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SITE_DIR="${SPC_STORY_OUTPUT_DIR:-$HOME/spc-outlook-site/stories}"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

PYTHON3="$(command -v python3)"
CLOUDFLARED="$(command -v cloudflared || true)"
if [ -z "$CLOUDFLARED" ]; then
  echo "cloudflared not found on PATH -- install it first (e.g. 'brew install cloudflared')." >&2
  exit 1
fi

mkdir -p "$LAUNCH_AGENTS" "$REPO_DIR/deploy/logs" "$SITE_DIR"

render() {
  sed \
    -e "s#__REPO_DIR__#$REPO_DIR#g" \
    -e "s#__SITE_DIR__#$SITE_DIR#g" \
    -e "s#__PYTHON3__#$PYTHON3#g" \
    -e "s#__CLOUDFLARED__#$CLOUDFLARED#g" \
    "$1"
}

render "$REPO_DIR/deploy/com.metamagicdev.spc-outlook-web.plist.template" \
  > "$LAUNCH_AGENTS/com.metamagicdev.spc-outlook-web.plist"
render "$REPO_DIR/deploy/com.metamagicdev.spc-outlook-tunnel.plist.template" \
  > "$LAUNCH_AGENTS/com.metamagicdev.spc-outlook-tunnel.plist"

for label in com.metamagicdev.spc-outlook-web com.metamagicdev.spc-outlook-tunnel; do
  launchctl unload "$LAUNCH_AGENTS/$label.plist" 2>/dev/null || true
  launchctl load "$LAUNCH_AGENTS/$label.plist"
done

echo "Installed and started:"
echo "  - com.metamagicdev.spc-outlook-web    (serves $SITE_DIR on http://127.0.0.1:8787)"
echo "  - com.metamagicdev.spc-outlook-tunnel (cloudflared tunnel run spc-outlook)"
echo
echo "Logs: $REPO_DIR/deploy/logs/"
echo "Make sure spc_story_generator.py writes to the same directory: export SPC_STORY_OUTPUT_DIR=$SITE_DIR"
