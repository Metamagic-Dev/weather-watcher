#!/usr/bin/env python3
"""
Serves the local SPC outlook site so the Cloudflare Tunnel can expose it.

Runs as a persistent background service (see ../deploy/) on the Mac Mini,
independent of the GitHub Actions runner -- spc_story_generator.py just
writes new files into this same directory between requests, and this
process keeps serving whatever's currently on disk. Nothing here ever talks
to GitHub; the pictures live only on this machine.
"""
import http.server
import os
import socketserver

DIRECTORY = os.environ.get("SPC_STORY_OUTPUT_DIR", os.path.expanduser("~/spc-outlook-site/stories"))
PORT = int(os.environ.get("SPC_STORY_WEB_PORT", "8787"))


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        # The entire point of this page is "the latest pictures" -- a
        # cached index.html or image would keep showing a previous run's
        # slides after clear_output_dir() replaces them, so caching is
        # disabled outright rather than relying on cache-busting query
        # strings or ETags.
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()


def main():
    os.makedirs(DIRECTORY, exist_ok=True)
    # Bind to localhost only -- cloudflared is what actually exposes this
    # to the internet (see ../deploy/cloudflared-config.yml), so the local
    # port itself doesn't need to (and shouldn't) be reachable on the LAN.
    with socketserver.TCPServer(("127.0.0.1", PORT), NoCacheHandler) as httpd:
        print(f"Serving {DIRECTORY} on http://127.0.0.1:{PORT}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
