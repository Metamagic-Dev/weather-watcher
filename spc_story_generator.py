#!/usr/bin/env python3
"""
Generate Instagram Story slides from SPC's Day 1-3 Convective Outlooks.

Each day is checked independently and only produces slides when its highest
categorical risk is Enhanced (ENH), Moderate (MDT), or High (HIGH), OR when
SPC has drawn a hatched ("significant", ~EF2+) tornado risk area for that
day -- that can appear on days whose categorical risk is only
Marginal/Slight, so it's checked independently. A day that doesn't clear
either bar is skipped, but a notification still goes out either way (summing
up every day checked) so silence doesn't get mistaken for the script having
failed.

Data sources (public, no API key required):
  - Categorical risk polygons: SPC's own GeoJSON export, one per day
  - Map graphic: SPC's official outlook image, one per day

Colors for each risk category are read directly from the GeoJSON's own
'fill'/'stroke' properties rather than hardcoded, so this stays correct
even if SPC tweaks their palette.

Day 2 publishes the same per-hazard (tornado/wind/hail) probability layers
and hatched-tornado layer as Day 1. Day 3 only publishes a combined
categorical outlook -- no per-hazard breakdown, no hatched-tornado layer --
so its hazards slide is simply skipped. Day 4-8 isn't covered: SPC doesn't
publish a static map image for that product (it's rendered dynamically
in-browser), and its risk labels are probabilistic (15/30/40%/MDT) rather
than the ENH/MDT/HIGH categorical scheme this script's trigger is built on.
"""
import io
import os
import re
import sys
import datetime
import requests
from PIL import Image, ImageDraw, ImageFont

BASE = "https://www.spc.noaa.gov/products/outlook"

# Slide order for the hazards-combined slide follows SPC's own convention
# (tornado, wind, hail).
HAZARD_SUFFIXES = (
    ("torn", "TORNADO OUTLOOK"),
    ("wind", "WIND OUTLOOK"),
    ("hail", "HAIL OUTLOOK"),
)


def hazards_for_day(day):
    """Per-hazard probability layers for a given outlook day -- each has its
    own GeoJSON (for the peak percentage + its official color) and its own
    SPC map graphic. Only Day 1 and Day 2 publish these."""
    return tuple(
        (suffix, title, f"{BASE}/day{day}otlk_{suffix}.nolyr.geojson", f"{BASE}/day{day}probotlk_{suffix}.png")
        for suffix, title in HAZARD_SUFFIXES
    )


# One entry per outlook day this script checks. `sigtorn_url` is None for
# days that don't publish a hatched-tornado layer (Day 3); `hazards` is
# empty for days with no per-hazard probability breakdown (Day 3).
DAY_CONFIGS = (
    {
        "day": 1,
        "cat_url": f"{BASE}/day1otlk_cat.nolyr.geojson",
        "sigtorn_url": f"{BASE}/day1otlk_sigtorn.nolyr.geojson",
        "map_url": f"{BASE}/day1otlk.png",
        "hazards": hazards_for_day(1),
    },
    {
        "day": 2,
        "cat_url": f"{BASE}/day2otlk_cat.nolyr.geojson",
        "sigtorn_url": f"{BASE}/day2otlk_sigtorn.nolyr.geojson",
        "map_url": f"{BASE}/day2otlk.png",
        "hazards": hazards_for_day(2),
    },
    {
        "day": 3,
        "cat_url": f"{BASE}/day3otlk_cat.nolyr.geojson",
        "sigtorn_url": None,
        "map_url": f"{BASE}/day3otlk.png",
        "hazards": (),
    },
)

# Defaults to a folder INSIDE the repo checkout -- the workflow commits and
# pushes this folder so images (a) are the actual delivery mechanism (pulled
# by the iOS Shortcut) and (b) generate the commit activity that keeps GitHub
# from auto-disabling the schedule after 60 quiet days. See rotate_old_slides()
# for cleanup.
OUTPUT_DIR = os.environ.get("SPC_STORY_OUTPUT_DIR", "./stories")
KEEP_RECENT = int(os.environ.get("SPC_STORY_KEEP_RECENT", "5"))

NTFY_TOPIC = os.environ.get("SPC_NTFY_TOPIC")  # optional: push notification via ntfy.sh

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


def format_effective_window(props):
    """SPC's own VALID/EXPIRE timestamps for the featured risk polygon --
    i.e. when the risk is actually in effect, which can differ from both
    the bulletin's issuance time and whenever this script happens to run."""
    start = datetime.datetime.fromisoformat(props["VALID_ISO"])
    end = datetime.datetime.fromisoformat(props["EXPIRE_ISO"])
    if start.date() == end.date():
        return f"EFFECTIVE {start:%H:%M}-{end:%H:%M} UTC {start:%b %d}".upper()
    return f"EFFECTIVE {start:%b %d %H:%M} - {end:%b %d %H:%M} UTC".upper()


def has_significant_tornado_risk(sigtorn_url):
    """
    SPC's sigtorn layer is a single feature per day: DN=0 with empty
    geometry when there's no hatched area, or DN=10 (LABEL "SIGN") with
    real polygons when there is. Any nonzero DN means the hatch is present.
    """
    features = fetch_geojson(sigtorn_url).get("features", [])
    return any(f["properties"].get("DN", 0) for f in features)


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def rotate_old_slides(directory, keep):
    """
    Deletes all but the `keep` most recent story sets in `directory`.
    Written in Python rather than a shell one-liner on purpose: the obvious
    bash approach (`ls | sort | head -n -N`) relies on GNU head's negative
    -N, which doesn't exist in BSD head -- i.e. it silently breaks on macOS,
    which is exactly where this runs. Filenames encode their own sort order
    (YYYYMMDD_HHMM), so plain string sort is enough.

    Matches on the stamp prefix only (not a fixed suffix list) since a story
    set's slide count varies day to day -- some hazards have no probability
    area at all and are skipped entirely.
    """
    pattern = re.compile(r"^spc_story_(\d{8}_\d{4})_")
    stamps = sorted({m.group(1) for m in (pattern.match(f) for f in os.listdir(directory)) if m})
    for stamp in stamps[:-keep] if len(stamps) > keep else []:
        prefix = f"spc_story_{stamp}_"
        for f in os.listdir(directory):
            if f.startswith(prefix):
                os.remove(os.path.join(directory, f))


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
    # NB: ImageFont.load_default() with no size argument ignores `size`
    # entirely and returns Pillow's ancient ~10px bitmap font -- passing
    # size here is what keeps a missing bundled font a legible (if
    # inconsistent-looking) fallback instead of near-invisible text.
    return ImageFont.load_default(size=size)


MARGIN = 64
SAFE_TOP = 220  # keeps content clear of Instagram's profile/header chrome
SAFE_BOTTOM = 220  # keeps content clear of Instagram's reply-bar chrome

BG_TOP = (13, 15, 20)
BG_BOTTOM = (26, 29, 36)


def gradient_background():
    """Subtle top-to-bottom gradient so slides read as designed, not a flat void."""
    slide = Image.new("RGB", STORY_SIZE)
    draw = ImageDraw.Draw(slide)
    h = STORY_SIZE[1]
    for y in range(h):
        t = y / (h - 1)
        row = tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3))
        draw.line([(0, y), (STORY_SIZE[0], y)], fill=row)
    return slide


def fit_font(draw, text, max_width, size, bold=False, min_size=22, step=2):
    """Shrinks the point size until `text` fits max_width on one line."""
    font = load_font(size, bold=bold)
    while size > min_size:
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            break
        size -= step
        font = load_font(size, bold=bold)
    return font


def draw_header(draw, title, issued_label, accent_hex, day_eyebrow="SPC DAY 1 CONVECTIVE OUTLOOK"):
    max_w = STORY_SIZE[0] - 2 * MARGIN
    eyebrow_font = load_font(30, bold=True)
    title_font = fit_font(draw, title, max_w, 80, bold=True)
    sub_font = load_font(32)

    y = SAFE_TOP
    draw.rectangle([(MARGIN, y), (MARGIN + 64, y + 8)], fill=accent_hex)
    y += 26
    draw.text((MARGIN, y), day_eyebrow, font=eyebrow_font, fill=accent_hex)
    y += 42

    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    draw.text((MARGIN, y - title_bbox[1]), title, font=title_font, fill="white")
    y += (title_bbox[3] - title_bbox[1]) + 18

    draw.text((MARGIN, y), issued_label, font=sub_font, fill="#9a9fa8")
    y += 32 + 44
    return y  # y where header content ends


def draw_footer(draw, accent_hex, top=None):
    label_font = load_font(30, bold=True)
    pill_top = STORY_SIZE[1] - SAFE_BOTTOM - 76 if top is None else top
    text = "FULL OUTLOOK -> spc.noaa.gov"
    bbox = draw.textbbox((0, 0), text, font=label_font)
    text_w = bbox[2] - bbox[0]
    pill_w = text_w + 80
    pill = [(MARGIN, pill_top), (MARGIN + pill_w, pill_top + 76)]
    draw.rounded_rectangle(pill, radius=38, outline=accent_hex, width=3)
    draw.text((MARGIN + 40, pill_top + 22), text, font=label_font, fill=accent_hex)


def paste_bordered_map(slide, draw, map_img, x, y, w, h, accent_hex, border_w=3):
    """Scales `map_img` to fit within (w, h) -- preserving aspect ratio -- and
    pastes it centered in that box with a colored border. Returns the actual
    rendered (width, height), which is usually smaller than the box on
    whichever axis wasn't the binding constraint."""
    ratio = min(w / map_img.width, h / map_img.height)
    new_size = (int(map_img.width * ratio), int(map_img.height * ratio))
    resized = map_img.resize(new_size, Image.LANCZOS)
    pos = (x + (w - new_size[0]) // 2, y)
    border = [
        (pos[0] - border_w, pos[1] - border_w),
        (pos[0] + new_size[0] + border_w, pos[1] + new_size[1] + border_w),
    ]
    draw.rectangle(border, outline=accent_hex, width=border_w)
    slide.paste(resized, pos)
    return new_size


def draw_hazard_pill(draw, x, y, text, fill_hex, font_size, max_w):
    """A filled, rounded percentage badge (e.g. '45% WIND RISK') used above
    each hazard's mini-map in the combined hazards slide."""
    font = fit_font(draw, text, max_w - 40, font_size, bold=True)
    bbox = draw.textbbox((0, 0), text, font=font)
    pill_h = int(font_size * 1.6)
    pill_w = min(max_w, bbox[2] - bbox[0] + 40)
    draw.rounded_rectangle([(x, y), (x + pill_w, y + pill_h)], radius=pill_h // 2, fill=fill_hex)
    draw.text((x + 20, y + pill_h // 2 - (bbox[3] - bbox[1]) // 2 - bbox[1]), text, font=font, fill="black")
    return pill_h


def make_hero_map_slide(map_img, title, issued_label, banner_text, accent_hex, effective_text,
                         day_eyebrow="SPC DAY 1 CONVECTIVE OUTLOOK"):
    """
    Shared layout for the categorical outlook slide: header, a full-width
    colored banner (the categorical risk label), a prominent effective-time
    callout, and SPC's map graphic.
    """
    slide = gradient_background()
    draw = ImageDraw.Draw(slide)

    content_y = draw_header(draw, title, issued_label, accent_hex, day_eyebrow)

    # Hero banner sits right under the header, full width, so it reads as
    # the headline of the slide rather than an afterthought at the bottom.
    banner_top = content_y
    banner_h = 190
    draw.rectangle([(0, banner_top), (STORY_SIZE[0], banner_top + banner_h)], fill=accent_hex)
    banner_font = fit_font(draw, banner_text, STORY_SIZE[0] - 2 * MARGIN, 72, bold=True)
    bbox = draw.textbbox((0, 0), banner_text, font=banner_font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((STORY_SIZE[0] - text_w) // 2, banner_top + (banner_h - text_h) // 2 - bbox[1]),
        banner_text, font=banner_font, fill="black",
    )

    # Called out as its own bold, bordered pill right under the banner --
    # not buried in the small subtitle -- since when the risk window opens
    # and closes matters as much as the category itself.
    eff_top = banner_top + banner_h + 30
    eff_font = fit_font(draw, effective_text, STORY_SIZE[0] - 2 * MARGIN - 64, 40, bold=True)
    eff_bbox = draw.textbbox((0, 0), effective_text, font=eff_font)
    eff_text_w, eff_text_h = eff_bbox[2] - eff_bbox[0], eff_bbox[3] - eff_bbox[1]
    eff_pill_h = eff_text_h + 48
    eff_pill_w = eff_text_w + 64
    eff_pill = [
        ((STORY_SIZE[0] - eff_pill_w) // 2, eff_top),
        ((STORY_SIZE[0] + eff_pill_w) // 2, eff_top + eff_pill_h),
    ]
    draw.rounded_rectangle(eff_pill, radius=eff_pill_h // 2, outline=accent_hex, width=4)
    draw.text(
        ((STORY_SIZE[0] - eff_text_w) // 2, eff_top + (eff_pill_h - eff_text_h) // 2 - eff_bbox[1]),
        effective_text, font=eff_font, fill="white",
    )

    # Map is sized by width (its aspect ratio is always wider than tall) and
    # packed directly beneath the effective-time pill -- the footer then
    # follows right after the image instead of being pinned to the bottom
    # of the canvas, so there's no dead void regardless of image proportions.
    map_top = eff_top + eff_pill_h + 40
    max_w = STORY_SIZE[0] - 2 * MARGIN
    max_h_cap = STORY_SIZE[1] - SAFE_BOTTOM - 76 - 56 - map_top
    _, new_h = paste_bordered_map(slide, draw, map_img, MARGIN, map_top, max_w, max_h_cap, accent_hex, border_w=6)

    footer_top = map_top + new_h + 56
    draw_footer(draw, accent_hex, top=min(footer_top, STORY_SIZE[1] - SAFE_BOTTOM - 76))
    return slide


def make_hazards_combined_slide(hazard_data, issued_label, day_eyebrow="SPC DAY 1 CONVECTIVE OUTLOOK",
                                 title="HAZARD PROBABILITIES"):
    """
    One slide covering every hazard (tornado/wind/hail) that has a
    probability area today -- each hazard's own SPC map (with its own
    color-key legend baked in) plus a pill showing its peak percentage.

    - 3 hazards: the most prominent (highest DN) gets a full-width hero
      card on top; the other two sit side by side below it.
    - 1-2 hazards: stacked, full width, centered in the available space.

    `hazard_data` is a list of (title, map_img, pct_display, fill_hex, dn).
    """
    slide = gradient_background()
    draw = ImageDraw.Draw(slide)
    content_y = draw_header(draw, title, issued_label, "#9a9fa8", day_eyebrow)

    max_w = STORY_SIZE[0] - 2 * MARGIN
    footer_zone_top = STORY_SIZE[1] - SAFE_BOTTOM - 76 - 40
    available = footer_zone_top - content_y
    n = len(hazard_data)

    if n <= 2:
        pill_h_est, gap_after_pill, inter_card_gap = 64, 14, 28
        total_gaps = inter_card_gap * (n - 1)
        map_h = max(180, min(380, (available - total_gaps - n * (pill_h_est + gap_after_pill)) // max(n, 1)))
        total_content_h = n * (pill_h_est + gap_after_pill + map_h) + total_gaps

        y = content_y + max(0, (available - total_content_h) // 2)
        for _title, map_img, pct_display, fill_hex, _dn in hazard_data:
            ph = draw_hazard_pill(draw, MARGIN, y, pct_display.upper(), fill_hex, 40, max_w)
            y += ph + gap_after_pill
            paste_bordered_map(slide, draw, map_img, MARGIN, y, max_w, map_h, fill_hex)
            y += map_h + inter_card_gap
        footer_top = y - inter_card_gap + 30

    else:
        # Hero (most prominent hazard) full width on top, the other two
        # side by side below -- the columns' width fixes their map height
        # via aspect ratio, so that part of the layout doesn't flex; only
        # the hero's height flexes to fill whatever budget remains.
        ordered = sorted(hazard_data, key=lambda h: h[4], reverse=True)
        hero, rest = ordered[0], ordered[1:]

        col_gap = 28
        col_w = (max_w - col_gap) // 2
        col_map_h = int(col_w / hero[1].width * hero[1].height)
        col_pill_h_est = 54
        row_gap = 36
        bottom_block_h = col_pill_h_est + 12 + col_map_h

        hero_pill_h_est, hero_gap = 70, 16
        hero_map_h = max(220, min(520, available - row_gap - bottom_block_h - hero_pill_h_est - hero_gap))
        total_content_h = hero_pill_h_est + hero_gap + hero_map_h + row_gap + bottom_block_h

        y = content_y + max(0, (available - total_content_h) // 2)
        ph = draw_hazard_pill(draw, MARGIN, y, hero[2].upper(), hero[3], 44, max_w)
        y += ph + hero_gap
        paste_bordered_map(slide, draw, hero[1], MARGIN, y, max_w, hero_map_h, hero[3])
        y += hero_map_h + row_gap

        x = MARGIN
        row_top = y
        col_bottom = row_top
        for _title, map_img, pct_display, fill_hex, _dn in rest:
            ph2 = draw_hazard_pill(draw, x, row_top, pct_display.upper(), fill_hex, 30, col_w)
            cy = row_top + ph2 + 12
            paste_bordered_map(slide, draw, map_img, x, cy, col_w, col_map_h, fill_hex)
            col_bottom = max(col_bottom, cy + col_map_h)
            x += col_w + col_gap
        footer_top = col_bottom + 30

    draw_footer(draw, "#9a9fa8", top=min(footer_top, STORY_SIZE[1] - SAFE_BOTTOM - 76))
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


def notify(message):
    """
    Single text-only ntfy notification -- no attachments, so a multi-slide
    run is one push instead of one-per-slide. Slides themselves live on the
    `stories` branch (and an iOS Shortcut pulls the latest set from there),
    so ntfy only needs to announce the outcome. Fires every run, trigger or
    not, so silence never gets mistaken for the script having failed.
    """
    send_text_notification(message)
    if sys.platform == "darwin":
        # Local fallback if this happens to run on the Mac itself (not your phone).
        safe_msg = message.replace('"', "'")
        os.system(f'osascript -e \'display notification "{safe_msg}" with title "SPC Outlook"\'')


def check_day(day_cfg):
    """Fetches this day's categorical outlook (and its hatched-tornado
    layer, if it publishes one) and reports whether it clears the trigger
    bar. Returns (top_feature, top_label, sig_tornado, triggered)."""
    top = highest_risk_feature(fetch_geojson(day_cfg["cat_url"]).get("features", []))
    top_label = top["properties"].get("LABEL") if top else None

    sig_tornado = False
    if day_cfg["sigtorn_url"]:
        sig_tornado = has_significant_tornado_risk(day_cfg["sigtorn_url"])

    triggered = top_label in TRIGGER_LABELS or sig_tornado
    return top, top_label, sig_tornado, triggered


def build_day_slides(day_cfg, top):
    """Builds this day's hero map slide plus (if this day publishes
    per-hazard probability layers and any have area today) its hazards
    slide. Returns (list of (suffix, slide) pairs, risk_display)."""
    day = day_cfg["day"]
    props = top["properties"]
    issue_dt = datetime.datetime.fromisoformat(props["ISSUE_ISO"])
    issued_label = f"Day {day} Outlook -- Issued {issue_dt:%Y-%m-%d %H:%M} UTC"
    effective_text = format_effective_window(props)
    risk_display = props.get("LABEL2", props["LABEL"])
    day_eyebrow = f"SPC DAY {day} CONVECTIVE OUTLOOK"
    hero_title = "SEVERE WEATHER OUTLOOK" if day == 1 else f"DAY {day} OUTLOOK"

    map_img = download_map_image(day_cfg["map_url"])
    slides = [(f"day{day}_map", make_hero_map_slide(
        map_img, hero_title, issued_label, risk_display.upper(),
        props.get("fill", "#E6C120"), effective_text, day_eyebrow,
    ))]

    hazard_data = []
    for _suffix, title, geojson_url, image_url in day_cfg["hazards"]:
        hz_top = highest_risk_feature(fetch_geojson(geojson_url).get("features", []))
        # On a quiet day SPC still returns one feature -- a DN=0 placeholder
        # (e.g. LABEL "Less Than 2% All Areas") with no fill/stroke color --
        # rather than an empty features list. DN=0 is SPC's own convention
        # for "nothing drawn" (see has_significant_tornado_risk), so treat
        # it the same as no feature at all instead of trying to render it.
        if not hz_top or not hz_top["properties"].get("DN"):
            continue  # no probability area for this hazard today -- skip it
        hz_props = hz_top["properties"]
        hz_display = hz_props.get("LABEL2", hz_props.get("LABEL", "?"))
        hz_img = download_map_image(image_url)
        hazard_data.append((title, hz_img, hz_display, hz_props.get("fill", "#E6C120"), hz_props.get("DN", 0)))

    if hazard_data:
        slides.append((f"day{day}_hazards", make_hazards_combined_slide(
            hazard_data, issued_label, day_eyebrow, f"DAY {day} HAZARD PROBABILITIES",
        )))

    return slides, risk_display


def main():
    now = datetime.datetime.utcnow()
    slides = []
    summaries = []

    for day_cfg in DAY_CONFIGS:
        day = day_cfg["day"]
        top, top_label, sig_tornado, triggered = check_day(day_cfg)

        if not triggered:
            summaries.append(f"Day {day} '{top_label or 'none'}' -- below Enhanced, no hatched tornado risk.")
            continue

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        day_slides, risk_display = build_day_slides(day_cfg, top)
        slides.extend(day_slides)

        reason = risk_display
        if top_label not in TRIGGER_LABELS and sig_tornado:
            reason = f"{risk_display} (hatched significant tornado risk)"
        summaries.append(f"Day {day}: {reason}.")

    if not slides:
        message = "🌤️ No ENH+ in the 3 day outlook -- " + " ".join(summaries)
        print(message)
        notify(message)
        return

    stamp = now.strftime("%Y%m%d_%H%M")
    paths = []
    for i, (suffix, slide) in enumerate(slides, start=1):
        path = os.path.join(OUTPUT_DIR, f"spc_story_{stamp}_{i}_{suffix}.png")
        slide.save(path)
        print(f"Saved {path}")
        paths.append(path)

    rotate_old_slides(OUTPUT_DIR, KEEP_RECENT)

    notify("🚨 Outlook images generated! " + " ".join(summaries) + f" -- {len(paths)} story slide(s) ready in the repo.")


if __name__ == "__main__":
    main()
