# SPC Outlook Story Generator

Generates two Instagram Story-sized PNGs (1080x1920) whenever the SPC Day 1
Convective Outlook reaches **Enhanced** risk or higher:

1. `..._1_map.png` -- the official SPC map with a colored risk banner
2. `..._2_breakdown.png` -- a list of every risk category present, colored
   using SPC's own fill colors

If the highest risk is Marginal, Slight, or none, the script exits quietly
and produces no files.

**Generation still runs on your Mac (self-hosted runner). Delivery to your
phone happens via [ntfy](https://ntfy.sh), and the slides are also
committed to this repo** under `stories/`, keeping only the 5 most recent
sets. That commit does double duty:

- it's what keeps the images available beyond ntfy's attachment limits, and
- it's a real commit, which is what keeps GitHub from auto-disabling this
  scheduled workflow after 60 quiet days.

## How it works

- Pulls the categorical risk polygons from SPC's public GeoJSON export
  (`day1otlk_cat.nolyr.geojson`) and the official map graphic
  (`day1otlk.gif`) -- no API key needed.
- Risk severity comes from SPC's own `DN` field, and colors come from the
  GeoJSON's own `fill` property, so it doesn't rely on a hardcoded color
  table that could drift from SPC's actual palette.
- Renders slides with a bundled DejaVu Sans font (in `fonts/`) so text
  looks identical regardless of what OS actually runs the script.
- Rotates `stories/` down to the 5 most recent sets (10 files) before the
  workflow commits, so the repo doesn't grow without bound. Done in Python,
  not bash -- see the comment in `rotate_old_slides()` for why.
- Delivers each slide to your phone via ntfy, in one of two ways depending
  on `SPC_STORY_RAW_BASE_URL`:
  - **set** (repo/path is public): sends `Attach: <raw.githubusercontent
    URL>` pointing at the file just pushed. No 15 MB limit, no 3-hour
    expiry -- ntfy just references the URL.
  - **unset**: PUTs the file's bytes directly to ntfy (works with a
    private repo, but capped at ntfy's 15 MB size / 3-hour expiry).
  Also fires a local macOS notification as a fallback if it happens to run
  interactively on the Mac itself.

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

I also have not run the git-commit-and-push flow or the ntfy URL-attach
path end-to-end -- both are built directly against documented behavior
(GitHub Actions' default `GITHUB_TOKEN` push permissions, ntfy's
attach-from-URL semantics), but test both once before relying on them.

## Setup

```bash
pip3 install --user -r requirements.txt
python3 spc_story_generator.py
```

Check `./stories/` for slides (only appears on Enhanced+ days -- to force a
test run regardless of current risk, temporarily add a print of
`top_label` and lower the trigger set, or just test on a day SPC has an
Enhanced+ area up).

### One decision you need to make: public or private repo?

This only matters for the ntfy delivery mechanism, not for whether the
commit/60-day trick works (that part is unaffected by visibility):

- **Public repo (or you're fine making just this narrow slice public):**
  set `SPC_STORY_RAW_BASE_URL` in the workflow (already wired up to
  `raw.githubusercontent.com/<repo>/<branch>/stories`). You get
  no-size-limit, no-expiry delivery. Given the content is just NOAA's own
  public map data, this is what I'd default to unless you have a reason to
  keep the repo private.
- **Private repo:** leave `SPC_STORY_RAW_BASE_URL` unset. ntfy has no way
  to authenticate to fetch a private raw URL, so delivery falls back to
  direct-byte PUT -- back to the 15 MB / 3-hour constraints from before,
  but nothing else changes.

### Getting slides onto your phone

1. Install the [ntfy app](https://ntfy.sh/) on your phone, subscribe to a
   topic name of your choosing (**treat it like a password** -- ntfy's own
   docs say this explicitly, since there's no sign-up and anyone who knows
   the topic name can subscribe or publish to it).
2. Set it as a repo secret named `SPC_NTFY_TOPIC`.
3. When a slide is generated, you'll get a notification with the image
   attached (or linked, if public) -- tap it, then share straight to
   Instagram Stories.

The `stories/` folder in the repo and the workflow artifact are both
fallbacks if you ever miss a notification.

### Scheduling via GitHub Actions

`.github/workflows/spc-outlook-story.yml` runs on your self-hosted runner
~30-40 min after each of SPC's five daily Day 1 issuance times, then
commits any new slides. Things to double check:

- `runs-on: [self-hosted, macOS, ARM64]` -- change the labels to match
  whatever you actually tagged your M1 runner with.
- `permissions: contents: write` is set at the workflow level so the
  default `GITHUB_TOKEN` can push -- if your org/repo has tightened default
  token permissions below this, the push step will fail with a permissions
  error rather than silently doing nothing.
- Add `SPC_NTFY_TOPIC` (and optionally leave/remove `SPC_STORY_RAW_BASE_URL`
  per the public/private decision above) as repository secrets/variables.

## Blind spots / things I haven't solved for you

**The repo-commit approach itself (new, from this round)**
- **Repo bloat.** Rotation keeps the *working tree* to 5 sets, but git
  history keeps every blob from every commit forever by default. At maybe
  1-3 MB per slide x 2 slides x however many Enhanced+ days per year, this
  is a slow trickle, not a flood -- but if this lives inside your
  myCheckbook repo, every collaborator/CI clone carries that history
  forever. I'd genuinely recommend a **separate, dedicated repo** just for
  this bot rather than folding it into myCheckbook, specifically to keep
  weather-map history from bloating your app's repo.
- **That means a second self-hosted runner registration.** Self-hosted
  runners are registered per-repo (or per-org, if you have one) -- if you
  split this into its own repo, you'll need to register your Mac as a
  runner there too (same machine, second runner service/token), not just
  reuse the myCheckbook registration. I don't know whether your existing
  runner is repo-scoped or org-scoped, so I can't tell you which case
  you're in.
- **Winter/quiet-season gap.** The 60-day clock resets on *any* commit, and
  this workflow only commits on Enhanced+ days. In a long stretch with no
  Enhanced+ risk anywhere in CONUS (more plausible in winter), you could
  still hit 60 quiet days and get auto-disabled -- the fix (not yet built)
  would be a separate, infrequent heartbeat commit (e.g. monthly) as a
  backstop, independent of whether any story fired.
- **Push races.** I added `concurrency: cancel-in-progress: false` so
  overlapping scheduled runs queue instead of both trying to push at once,
  but I haven't tested this under real overlap.

**Delivery mechanism**
- ntfy's direct-byte fallback still expires attachments from ntfy.sh
  **3 hours** after sending -- only relevant if you go the private-repo
  route above.
- The topic name is effectively a password with no rotation/revocation UI
  beyond picking a new one. Don't reuse a topic name you use for anything
  sensitive.

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

- A monthly heartbeat commit as a backstop against the winter-quiet-season
  gap described above.
- A third slide breaking out tornado/hail/wind *probability* percentages
  (SPC publishes these as separate GeoJSON files: `day1otlk_torn`,
  `day1otlk_hail`, `day1otlk_wind`, same `.nolyr.geojson` pattern).
- Auto-detecting "significant severe" hatched areas (10%+ chance of
  EF2+/2"+ hail/65+kt wind), which SPC marks separately from the
  categorical risk.
