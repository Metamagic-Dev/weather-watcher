#!/usr/bin/env python3
"""
Generate Instagram Story slides from the SPC Day 1 Convective Outlook.

Only produces output when the highest categorical risk is Enhanced (ENH),
Moderate (MDT), or High (HIGH). Marginal/Slight/no-risk days are skipped.

Data sources (public, no API key required):
  - Categorical risk polygons: SPC's own GeoJSON export
  - Map graphic: SPC's official Day 1 outlook image

Colors for each risk category are read directly from the GeoJSON's own
'fill'/'stroke' properties rather than hardcoded, so this stays correct
even if SPC tweaks their palette.
"""
import io
import os
import re
import sys
import datetime
import requests
from PIL import Image, ImageDraw, ImageFont

BASE = "https://www.spc.noaa.gov/products/outlook"
CAT_GEOJSON_URL = f"{BASE}/day1otlk_cat.nolyr.geojson"
MAP_IMAGE_URL = f"{BASE}/day1otlk.png"

# Defaults to a folder INSIDE the repo checkout -- the workflow commits and
# pushes this folder so images (a) persist beyond ntfy's attachment expiry
# and (b) generate the commit activity that keeps GitHub from auto-disabling
# the schedule after 60 quiet days. See rotate_old_slides() for cleanup.
OUTPUT_DIR = os.environ.get("SPC_STORY_OUTPUT_DIR", "./stories")
KEEP_RECENT = int(os.environ.get("SPC_STORY_KEEP_RECENT", "5"))

NTFY_TOPIC = os.environ.get("SPC_NTFY_TOPIC")  # optional: push notification via ntfy.sh

# If set (e.g. https://raw.githubusercontent.com/you/repo/main/stories), slides
# are delivered to ntfy as a URL attachment pointing at the just-pushed commit
# -- no 15 MB size limit, no 3-hour expiry, since ntfy just references the URL
# instead of holding the bytes. Requires the repo (or at least this path) to
# be PUBLIC, since ntfy's server fetches the URL with no auth of its own.
# If unset, falls back to PUTting the raw file bytes to ntfy directly (works
# with a private repo, but subject to ntfy's 15 MB / 3-hour limits).
RAW_BASE_URL = os.environ.get("SPC_STORY_RAW_BASE_URL", "").rstrip("/")

# Categories worth posting about. SPC's own DN field gives severity order,
# so we don't need to hardcode a rank -- just a trigger threshold by label.
TRIGGER_LABELS = {"ENH", "MDT", "HIGH"}

STORY_SIZE = (1080, 1920)
HTTP_HEADERS = {"User-Agent": "spc-story-bot/1.0 (personal use)"}


def fetch_geojson(url):
    r = requests.get(url, timeout=30, headers=HTTP_HEADERS)
    r.raise_for_status()
    return r.json()


def download_map_image(url):
    r = requests.get(url, timeout=30, headers=HTTP_HEADERS)
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content)).convert("RGB")


def highest_risk_feature(features):
    """SPC's DN field is their own severity ranking -- just take the max."""
    if not features:
        return None
    return max(features, key=lambda f: f["properties"].get("DN", 0))


def summarize_rows(features):
    """One (label, display_text, fill_color) tuple per risk polygon, most severe first."""
    ordered = sorted(features, key=lambda f: f["properties"].get("DN", 0), reverse=True)
    rows = []
    for feat in ordered:
        p = feat["properties"]
        label = p.get("LABEL", "?")
        # LABEL2 isn't guaranteed present on every SPC geojson export -- fall back to LABEL.
        display = p.get("LABEL2", label)
        rows.append((label, display, p.get("fill", "#888888")))
    return rows


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def rotate_old_slides(directory, keep):
    """
    Deletes all but the `keep` most recent story sets in `directory`.
    Written in Python rather than a shell one-liner on purpose: the obvious
    bash approach (`ls | sort | head -n -N`) relies on GNU head's negative
    -N, which doesn't exist in BSD head -- i.e. it silently breaks on macOS,
    which is exactly where this runs. Filenames encode their own sort order
    (YYYYMMDD_HHMM), so plain string sort is enough.
    """
    pattern = re.compile(r"^spc_story_(\d{8}_\d{4})_1_map\.png$")
    stamps = sorted(m.group(1) for m in (pattern.match(f) for f in os.listdir(directory)) if m)
    for stamp in stamps[:-keep] if len(stamps) > keep else []:
        for suffix in ("1_map", "2_breakdown"):
            path = os.path.join(directory, f"spc_story_{stamp}_{suffix}.png")
            if os.path.exists(path):
                os.remove(path)


def load_font(size, bold=False):
    # Bundled font first -- this is what makes rendering identical whether
    # this runs on your Mac runner, a Linux box, or anywhere else. Don't
    # rely on system font paths (e.g. DejaVu isn't installed on macOS by
    # default, and .ttc collections need an index Pillow won't guess right).
    candidates = [
        os.path.join(SCRIPT_DIR, "fonts", f"DejaVuSans{'-Bold' if bold else ''}.ttf"),
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def make_map_slide(map_img, issued_label, risk_display, fill_hex):
    slide = Image.new("RGB", STORY_SIZE, "black")
    draw = ImageDraw.Draw(slide)

    # Fit the SPC map into the upper portion, leaving room for title + banner.
    max_w, max_h = STORY_SIZE[0] - 40, int(STORY_SIZE[1] * 0.62)
    ratio = min(max_w / map_img.width, max_h / map_img.height)
    new_size = (int(map_img.width * ratio), int(map_img.height * ratio))
    resized = map_img.resize(new_size, Image.LANCZOS)
    pos = ((STORY_SIZE[0] - new_size[0]) // 2, 260)
    slide.paste(resized, pos)

    title_font = load_font(64, bold=True)
    sub_font = load_font(36)
    draw.text((60, 90), "SEVERE WEATHER OUTLOOK", font=title_font, fill="white")
    draw.text((60, 175), issued_label, font=sub_font, fill="#cccccc")

    # Risk banner colored to match the highest category, using SPC's own fill color.
    banner_top = pos[1] + new_size[1] + 40
    draw.rectangle([(0, banner_top), (STORY_SIZE[0], banner_top + 160)], fill=fill_hex)
    risk_font = load_font(54, bold=True)
    draw.text((60, banner_top + 45), risk_display.upper(), font=risk_font, fill="black")

    return slide


def make_breakdown_slide(rows, issued_label):
    slide = Image.new("RGB", STORY_SIZE, "#111111")
    draw = ImageDraw.Draw(slide)
    title_font = load_font(58, bold=True)
    sub_font = load_font(34)
    row_font = load_font(42)

    draw.text((60, 100), "RISK BREAKDOWN", font=title_font, fill="white")
    draw.text((60, 178), issued_label, font=sub_font, fill="#aaaaaa")

    y = 320
    for _label, display, fill_hex in rows:
        draw.rectangle([(60, y), (140, y + 70)], fill=fill_hex)
        draw.text((165, y + 12), display, font=row_font, fill="white")
        y += 110

    draw.text((60, STORY_SIZE[1] - 140), "Full outlook: spc.noaa.gov", font=sub_font, fill="#888888")
    return slide


def send_text_notification(message):
    if not NTFY_TOPIC:
        return
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={"Title": "SPC Outlook"},
            timeout=10,
        )
    except requests.RequestException as e:
        print(f"ntfy text notification failed: {e}", file=sys.stderr)


def send_file_to_phone(path, title):
    """
    Delivers one slide to your phone via ntfy, using whichever mechanism is
    configured:

    - RAW_BASE_URL set: sends an "Attach: <url>" pointing at the file that
      was just committed and pushed to GitHub. No 15 MB limit, no 3-hour
      expiry (verified against ntfy's docs -- externally-hosted attachments
      aren't subject to those). Requires that URL to be publicly fetchable.
    - RAW_BASE_URL unset: PUTs the local file's bytes directly as the
      notification body (works with a private repo, but bound by ntfy's
      15 MB size limit and 3-hour attachment expiry).
    """
    if not NTFY_TOPIC:
        print(f"SPC_NTFY_TOPIC not set -- skipping phone delivery of {path}")
        return
    filename = os.path.basename(path)
    headers = {"Title": title, "Tags": "warning"}
    try:
        if RAW_BASE_URL:
            headers["Attach"] = f"{RAW_BASE_URL}/{filename}"
            headers["Filename"] = filename
            requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", headers=headers, timeout=15)
        else:
            headers["Filename"] = filename
            with open(path, "rb") as f:
                requests.put(f"https://ntfy.sh/{NTFY_TOPIC}", data=f, headers=headers, timeout=30)
    except requests.RequestException as e:
        print(f"ntfy delivery failed for {path}: {e}", file=sys.stderr)


def notify_with_slides(risk_display, slide_paths):
    send_text_notification(f"{risk_display} risk today -- {len(slide_paths)} story slide(s) incoming.")
    for i, path in enumerate(slide_paths, start=1):
        send_file_to_phone(path, f"SPC Outlook -- slide {i}/{len(slide_paths)}")
    if sys.platform == "darwin":
        # Local fallback if this happens to run on the Mac itself (not your phone).
        safe_msg = f"{risk_display} risk today -- slides ready.".replace('"', "'")
        os.system(f'osascript -e \'display notification "{safe_msg}" with title "SPC Outlook"\'')


def main():
    cat = fetch_geojson(CAT_GEOJSON_URL)
    features = cat.get("features", [])
    top = highest_risk_feature(features)
    top_label = top["properties"].get("LABEL") if top else None

    if top_label not in TRIGGER_LABELS:
        print(f"Highest Day 1 categorical risk is '{top_label or 'none'}' -- below Enhanced, skipping.")
        return

    props = top["properties"]
    now = datetime.datetime.utcnow()
    issued_label = f"Day 1 Outlook -- {now:%Y-%m-%d %H:%M} UTC"

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    map_img = download_map_image(MAP_IMAGE_URL)
    rows = summarize_rows(features)
    risk_display = props.get("LABEL2", props["LABEL"])

    slide1 = make_map_slide(map_img, issued_label, risk_display, props.get("fill", "#E6C120"))
    slide2 = make_breakdown_slide(rows, issued_label)

    stamp = now.strftime("%Y%m%d_%H%M")
    path1 = os.path.join(OUTPUT_DIR, f"spc_story_{stamp}_1_map.png")
    path2 = os.path.join(OUTPUT_DIR, f"spc_story_{stamp}_2_breakdown.png")
    slide1.save(path1)
    slide2.save(path2)

    print(f"Saved {path1}")
    print(f"Saved {path2}")
    rotate_old_slides(OUTPUT_DIR, KEEP_RECENT)
    notify_with_slides(risk_display, [path1, path2])


if __name__ == "__main__":
    main()
