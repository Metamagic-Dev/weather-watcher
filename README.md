# SPC Outlook Story Generator

Generates a set of Instagram Story-sized PNGs (1080x1920) for each of SPC's
**Day 1, Day 2, and Day 3 Convective Outlooks**, checked independently.
A given day only produces slides when that day's outlook reaches
**Enhanced** risk or higher, or whenever SPC draws a **hatched
(significant, ~EF2+) tornado risk** area for that day -- which can appear
even on Marginal/Slight days (Day 3 doesn't publish this hatched layer, so
it's checked by categorical risk alone). Day 4-8 isn't covered: SPC doesn't
publish a static map image for that product, and it uses a different,
probabilistic-only risk scheme (15/30/40%/MDT) instead of the
ENH/MDT/HIGH categories this script's trigger is built on.

Each triggered day gets:

1. `..._dayN_map.png` -- that day's official categorical outlook map with a
   colored risk banner and a bold "EFFECTIVE ..." callout showing SPC's own
   valid/expire window for the risk
2. `..._dayN_hazards.png` -- **Day 1 and Day 2 only** (Day 3 doesn't publish
   a per-hazard breakdown): every hazard (tornado/wind/hail) that actually
   has a probability area that day, each with SPC's own probability map
   graphic and a pill badge showing that hazard's peak percentage:
   - **3 hazards present**: the most prominent one (highest peak
     percentage) is a full-width hero card on top; the other two sit side
     by side below it.
   - **1-2 hazards present**: stacked full width instead.
   - A hazard with no probability contour at all that day (e.g. no wind
     risk drawn anywhere) is left out entirely, and this slide is skipped
     if none of the three have any area.

Slides from every triggered day are combined into one run -- e.g. if only
Day 2 clears the bar, you get 1-2 slides; if all three days do, up to 6.

There's intentionally no separate "risk breakdown"/legend slide -- SPC's own
map graphics already bake a color-key legend into the corner of the image,
so a second slide repeating it as a list added a redundant screen instead of
new information. Splitting out tornado/wind/hail instead gives each hazard
its own real data (peak %, its own map) rather than restating the
categorical color key.

If none of Day 1/2/3 reach Enhanced and none have a hatched tornado area,
the script produces no files -- but it still sends a single ntfy
notification summarizing all three days, precisely so you know the check
ran and there's nothing to worry about, rather than wondering whether it
silently failed.

**Generation runs on your Mac (self-hosted runner), and the slides never
leave it.** GitHub only hosts the script and the Actions automation --
pictures are written straight to a folder on the Mac, which a small local
web server (`site/server.py`) serves over a **Cloudflare Tunnel**, so you
can open a private URL on your phone and download the latest set. Each
triggered run **deletes whatever the previous run left on disk** before
writing the new set (see `clear_output_dir()`) -- there's no archive, only
the latest pictures are ever present on the device. A single
[ntfy](https://ntfy.sh) text notification (with the site link) pings your
phone when new ones are ready. See "Local download site (Cloudflare
Tunnel)" below for the one-time setup.

## How it works

- Checks Day 1, Day 2, and Day 3 independently (see `DAY_CONFIGS` in
  `spc_story_generator.py`), each against its own categorical GeoJSON
  export (e.g. `day2otlk_cat.nolyr.geojson`) and official map graphic
  (e.g. `day2otlk.png`) -- no API key needed. Day 1 and Day 2 each pull a
  matching per-hazard pair too (e.g. `day2otlk_torn.nolyr.geojson` +
  `day2probotlk_torn.png`); Day 3 doesn't publish that breakdown, so its
  `hazards` list is empty and its hazards slide is skipped entirely. The
  hatched-tornado check is a separate SPC export per day (e.g.
  `day2otlk_sigtorn.nolyr.geojson`; Day 3 doesn't publish one, so it's
  checked by categorical risk alone) -- a single feature per day, `DN=0`
  with empty geometry when there's no hatched area, `DN=10` (`LABEL`
  `"SIGN"`) with real polygons when there is.
- Each slide's "EFFECTIVE ..." callout and its small issued-time subtitle
  both come from SPC's own `VALID_ISO`/`EXPIRE_ISO`/`ISSUE_ISO` fields on
  the outlook's own top risk feature -- not the time this script happens to
  run -- so they reflect the actual bulletin, not the polling cadence.
- Risk severity comes from SPC's own `DN` field, and colors come from the
  GeoJSON's own `fill` property, so it doesn't rely on a hardcoded color
  table that could drift from SPC's actual palette. The hazard slide's
  hero (when all 3 are present) is picked by comparing `DN` too. On a quiet
  day, SPC's per-hazard GeoJSON still returns one placeholder feature
  (`DN=0`, e.g. `LABEL` `"Less Than 2% All Areas"`, no fill color) rather
  than an empty list -- the script treats `DN=0` the same as "nothing
  drawn" so it doesn't try to render that placeholder.
- Renders slides with a bundled DejaVu Sans font (in `fonts/`) so text
  looks identical regardless of what OS actually runs the script.
- On a triggered run, `clear_output_dir()` deletes every file already in
  the output folder before the new slides are written -- so the folder (and
  the site) only ever contains the single latest run's files (1-6 images,
  depending on how many of the three days triggered and whether each had a
  hazard breakdown), never a mix of two runs and never an archive. A run
  that doesn't trigger leaves the previous set in place untouched, so the
  site always has *something* current to show.
- Also writes an `index.html` download page into the output folder
  alongside the images (see `write_index_html()`) -- this is what
  `site/server.py` serves at `/`.
- Sends a single text-only ntfy notification every run, trigger or not,
  summarizing every day checked -- e.g. "Day 1: Enhanced Risk. Day 2: 'SLGT'
  -- below Enhanced, no hatched tornado risk. Day 3: 'TSTM' -- below
  Enhanced, no hatched tornado risk." plus the site URL when
  `SPC_STORY_SITE_URL` is set. No image attachments, so a trigger run is
  one push instead of one per slide. Also fires a local macOS notification
  as a fallback if it happens to run interactively on the Mac itself.
- The actual images are picked up by visiting the Cloudflare Tunnel URL
  (see "Local download site (Cloudflare Tunnel)" below) -- nothing is ever
  pushed to GitHub.

## What I verified vs. assumed

I confirmed the GeoJSON URL pattern, the `ENH`/`MDT`/`HIGH` label values,
and the `DN`/`fill` fields against SPC's public docs and an open-source
project that parses the same files. I could **not** fetch a live copy of
the file directly (SPC's robots.txt blocks my fetch tool), so I couldn't
100% confirm every property name on the current live export -- in
particular `LABEL2` (the friendly display text) may or may not be present
on the categorical file specifically. The script falls back to `LABEL`
(e.g. `"ENH"`) if `LABEL2` is missing, so it won't break, but **run it
once manually and check the output before trusting the schedule.**

The `day1otlk_sigtorn.nolyr.geojson` schema (the hatched-tornado trigger),
by contrast, *was* confirmed live: fetched the current empty-day response
(single feature, `DN=0`, empty `GeometryCollection`) and cross-checked
against a real hatched day's shapefile from SPC's archive
(`day1otlk_20240506_1630_sigtorn.dbf`, the May 6, 2024 outbreak), which
confirmed `DN=10`/`LABEL="SIGN"` on an active hatch.

I also have not run the heartbeat-commit-and-push flow or the ntfy
notification path end-to-end -- both are built directly against documented
behavior (GitHub Actions' default `GITHUB_TOKEN` push permissions, ntfy's
text-push semantics), but test both once before relying on them.

## Setup

```bash
pip3 install --user -r requirements.txt
python3 spc_story_generator.py
```

Check `~/spc-outlook-site/stories/` for slides (only appears on Enhanced+
days or days with a hatched tornado area -- to force a test run regardless
of current risk, temporarily add a print of `top_label`/`sig_tornado` and
lower the trigger set, or just test on a day SPC has one of those up). Set
`SPC_STORY_OUTPUT_DIR` to point somewhere else if you don't want the
default location.

### Local download site (Cloudflare Tunnel)

The Mac needs two things running **continuously in the background**,
independent of when GitHub Actions happens to run the generator:
`site/server.py` (serves the pictures) and `cloudflared` (exposes that
server to the internet). `deploy/install.sh` installs both as launchd
services so they start at login and restart if they ever crash.

One-time setup, run directly on the Mac Mini:

1. **Install cloudflared**: `brew install cloudflared`
2. **Authenticate**: `cloudflared tunnel login` -- opens a browser to pick
   the Cloudflare account/zone (domain) this tunnel will attach to.
3. **Create the tunnel**: `cloudflared tunnel create spc-outlook` -- prints
   a UUID and writes credentials to `~/.cloudflared/<UUID>.json`.
4. **Route a hostname to it**:
   `cloudflared tunnel route dns spc-outlook spc-outlook.yourdomain.com`
   (any subdomain of a domain in your Cloudflare account).
5. **Configure the tunnel**: copy `deploy/cloudflared-config.yml` to
   `~/.cloudflared/config.yml` and fill in the tunnel UUID, the
   credentials-file path, and the hostname from steps 3-4.
6. **Install the services**: from a checkout of this repo on the Mac, run
   `./deploy/install.sh`. It generates the two launchd plists from the
   templates in `deploy/` (filling in absolute paths for `python3`,
   `cloudflared`, and this checkout), installs them to
   `~/Library/LaunchAgents/`, and starts both. Logs land in
   `deploy/logs/`.
7. **Verify**: visit `https://spc-outlook.yourdomain.com` -- you should see
   the download page (empty until the first slides are generated).
8. **Optional**: add that URL as a repository variable named
   `SPC_STORY_SITE_URL` so it gets appended to the ntfy notification --
   tapping the notification then takes you straight to the page.

Nothing about this setup is tied to a GitHub Actions run -- the generator
(triggered by the schedule below) just needs to write into the same folder
`site/server.py` is serving, which is why both default to
`~/spc-outlook-site/stories` unless you override `SPC_STORY_OUTPUT_DIR` in
both places. Since the download page and the images themselves are marked
`no-store`, refreshing the browser after a new run always shows the latest
set immediately.

### Scheduling via GitHub Actions

`.github/workflows/spc-outlook-story.yml` runs on your self-hosted runner
~30-40 min after each of SPC's five daily Day 1 issuance times. Day 2
(issued ~0600Z/1730Z) and Day 3 (issued ~0730Z) are checked on that same
Day 1-driven schedule rather than their own -- each run just re-fetches
whatever Day 2/3 outlook is currently live, so a Day 2/3 update between
polls won't generate a fresh story until the next scheduled check, same
caveat as an out-of-cycle Day 1 upgrade (see "SPC data itself" below).
Things to double check:

- `runs-on: [self-hosted, macOS, ARM64]` -- change the labels to match
  whatever you actually tagged your M1 runner with.
- `permissions: contents: write` is set at the workflow level so the
  default `GITHUB_TOKEN` can push the heartbeat commit (see below) -- if
  your org/repo has tightened default token permissions below this, that
  step will fail with a permissions error rather than silently doing
  nothing. No picture ever gets committed, so this permission is
  intentionally narrower in effect than it looks.
- Add `SPC_NTFY_TOPIC` as a repository secret, and optionally
  `SPC_STORY_SITE_URL` as a repository variable (see step 8 above).
- **Heartbeat commit, not a picture commit:** every run (trigger or not)
  touches a one-line timestamp in `heartbeat.txt` on the separate,
  unprotected `stories` branch and pushes it. This is the *only* thing
  that still gets committed to GitHub -- it exists purely so GitHub sees
  commit activity and doesn't auto-disable the schedule after 60 quiet
  days (a real risk in a long stretch with no Enhanced+ weather anywhere
  in CONUS, e.g. winter). If you don't care about that risk, you can
  delete this step, but there's no other reason to keep it since the
  actual slides never go there.

## Blind spots / things I haven't solved for you

**The local-site approach itself (new, from this round)**
- **Old picture history is gone from GitHub going forward, but not
  instantly purged.** I deleted the previously-committed slide PNGs from
  the `stories` branch tip in a normal commit, and no new pictures will
  ever be committed again -- but git history keeps old blobs around until
  something rewrites it (`git gc`, a history rewrite + force-push), which
  I did not do since that's destructive and wasn't asked for. If you want
  those old blobs fully gone, that's a deliberate follow-up, not something
  this change did silently.
- **The Mac has to actually be on and reachable for the site to work,
  independent of Actions.** Unlike before (where "did the workflow run"
  was the only thing that mattered), the download page now depends on two
  *always-on* launchd services (`site/server.py` and `cloudflared`) staying
  up between runs, not just during them. If the Mac reboots and those
  services don't restart (`KeepAlive`/`RunAtLoad` should handle this, but
  it's unverified end-to-end), the site goes dark even though the
  generator keeps running fine on its own schedule.
- **Heartbeat commit still needed, now for a different reason.** Removing
  the picture commits also removed the thing that was *accidentally*
  keeping GitHub's 60-day auto-disable clock reset. The workflow now pushes
  a one-line `heartbeat.txt` timestamp every run instead (see "Scheduling
  via GitHub Actions" above) -- untested end-to-end like the rest of the
  push flow.
- **Push races.** I added `concurrency: cancel-in-progress: false` so
  overlapping scheduled runs queue instead of both trying to push the
  heartbeat at once, but I haven't tested this under real overlap.

**Delivery mechanism**
- The Cloudflare Tunnel hostname is effectively the new "password" for
  reaching the site (nothing enforces auth on it by default) -- anyone who
  guesses or is given the URL can view/download the current slides. Add a
  Cloudflare Access policy on the hostname if you want to lock it down
  further; not set up here since you didn't ask for auth.
- The ntfy topic name is still effectively a password too, same as before,
  with no rotation/revocation UI beyond picking a new one.

**The self-hosted runner itself**
- GitHub's `schedule` trigger only fires if a runner is online to pick up
  the job -- your Mac needs to be **awake, logged into a user session, and
  running the Actions runner service** at each scheduled time. If it's
  asleep or the runner's stopped, that cycle is silently skipped (no retry).
- GitHub documents `schedule` as best-effort with no timing SLA -- during
  high load, runs can slip by minutes to tens of minutes.

**SPC data itself**
- The five issuance times (0600/1300/1630/2000/0100Z) are typical, not
  guaranteed -- SPC can run late, and NOAA's site may sit behind caching
  that serves a stale file for a few minutes after issuance.
- SPC sometimes updates outlooks **outside** the 5 standard issuance times
  (upgraded to Moderate/High mid-cycle, special statements). This script
  only checks at the times you've scheduled, so a risk upgrade between
  polls won't trigger a fresh story until the next scheduled check.
- `LABEL2` (the human-readable risk text) isn't 100% confirmed to exist on
  the categorical GeoJSON specifically -- falls back to `LABEL` if missing.
  Applies to Day 1, 2, and 3 alike since they share the same schema.

**Image/Instagram specifics**
- Instagram frequently re-compresses shared images and can crop/pad
  depending on the client version -- the story-safe zone assumptions here
  aren't pixel-verified against IG's current app.
- Fully automating actual *posting* (not just generation) is a separate,
  heavier lift via Meta's Graph API -- Business/Creator account, app
  review, publicly-hosted image URL required. Not addressed here since
  you said you'll post manually.

**True on-phone generation**
Compute still happens on your Mac; only delivery reaches the phone.
Rebuilding the actual image compositing natively on iOS (no Mac at all)
would mean something like Pythonista, since Shortcuts can't do colored
banner/text compositing the way Pillow does here. That's a separate
project, not a tweak to this one.

## Possible next steps (not built yet)

- A Cloudflare Access policy (or similar) in front of the download site --
  right now the tunnel hostname itself is the only thing gating access.
- Auto-detecting hatched significant-severe areas for **hail and wind**
  (`day1otlk_sighail.nolyr.geojson` / `day1otlk_sigwind.nolyr.geojson`
  exist alongside `day1otlk_sigtorn.nolyr.geojson` and follow the same
  `DN=0`/`DN=10` convention) -- only the tornado one is wired in as a
  trigger today.
- Extending to SPC's **Day 4-8 outlook** for a full week of lead time.
  Deliberately left out of this round: that product has no static map
  image (SPC renders it dynamically in-browser, so a map slide would mean
  building a renderer from the raw polygon GeoJSON), and its risk scheme is
  probabilistic-only (15/30/40%/MDT) rather than categorical, so it'd need
  its own trigger rule instead of reusing `TRIGGER_LABELS`.
