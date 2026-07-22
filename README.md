# SPC Outlook Story Generator

Generates a set of Instagram Story-sized PNGs (1080x1920) whenever the SPC
Day 1 Convective Outlook reaches **Enhanced** risk or higher, or whenever
SPC draws a **hatched (significant, ~EF2+) tornado risk** area -- which can
appear even on Marginal/Slight days:

1. `..._1_map.png` -- the official categorical outlook map with a colored
   risk banner
2. `..._2_hazards.png` -- every hazard (tornado/wind/hail) that actually has
   a probability area today, each with SPC's own probability map graphic and
   a pill badge showing that hazard's peak percentage:
   - **3 hazards present**: the most prominent one (highest peak
     percentage) is a full-width hero card on top; the other two sit side
     by side below it.
   - **1-2 hazards present**: stacked full width instead.
   - A hazard with no probability contour at all today (e.g. no wind risk
     drawn anywhere) is left out entirely, and this slide is skipped if
     none of the three have any area.

There's intentionally no separate "risk breakdown"/legend slide -- SPC's own
map graphics already bake a color-key legend into the corner of the image,
so a second slide repeating it as a list added a redundant screen instead of
new information. Splitting out tornado/wind/hail instead gives each hazard
its own real data (peak %, its own map) rather than restating the
categorical color key.

If the highest categorical risk is below Enhanced and there's no hatched
tornado area, the script produces no files -- but it still sends a single
ntfy notification saying so, precisely so you know the check ran and there's
nothing to worry about, rather than wondering whether it silently failed.

**Generation still runs on your Mac (self-hosted runner). The slides are
committed to the `stories` branch** under `stories/` (keeping only the 5
most recent sets), and a single [ntfy](https://ntfy.sh) text notification
pings your phone when new ones are ready -- an iOS Shortcut then pulls the
latest set straight from the branch. That commit does double duty:

- it's what makes the images available at all (the iOS Shortcut reads
  straight from here), and
- it's a real commit, which is what keeps GitHub from auto-disabling this
  scheduled workflow after 60 quiet days.

## How it works

- Pulls the categorical risk polygons from SPC's public GeoJSON export
  (`day1otlk_cat.nolyr.geojson`) and the official map graphic
  (`day1otlk.png`) -- no API key needed. Each hazard pulls the matching
  pair (e.g. `day1otlk_torn.nolyr.geojson` + `day1probotlk_torn.png`) the
  same way. The hatched-tornado check is a separate SPC export,
  `day1otlk_sigtorn.nolyr.geojson` -- a single feature per day, `DN=0`
  with empty geometry when there's no hatched area, `DN=10` (`LABEL`
  `"SIGN"`) with real polygons when there is.
- Risk severity comes from SPC's own `DN` field, and colors come from the
  GeoJSON's own `fill` property, so it doesn't rely on a hardcoded color
  table that could drift from SPC's actual palette. The hazard slide's
  hero (when all 3 are present) is picked by comparing `DN` too.
- Renders slides with a bundled DejaVu Sans font (in `fonts/`) so text
  looks identical regardless of what OS actually runs the script.
- Rotates `stories/` down to the 5 most recent sets (1-2 files each,
  depending on whether any hazard had a probability area that day) before
  the workflow commits, so the repo doesn't grow without bound. Done in
  Python, not bash -- see the comment in `rotate_old_slides()` for why.
- Sends a single text-only ntfy notification every run, trigger or not --
  either "ENH risk today -- 2 story slide(s) ready in the repo." or, on a
  quiet day, "Highest Day 1 categorical risk is 'SLGT' -- below Enhanced,
  no hatched tornado risk. Nothing generated." No image attachments, so a
  trigger run is one push instead of one per slide. Also fires a local
  macOS notification as a fallback if it happens to run interactively on
  the Mac itself.
- The actual images are picked up separately by an iOS Shortcut that reads
  the `stories` branch (see "Getting slides onto your phone" below).

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

I also have not run the git-commit-and-push flow or the ntfy URL-attach
path end-to-end -- both are built directly against documented behavior
(GitHub Actions' default `GITHUB_TOKEN` push permissions, ntfy's
attach-from-URL semantics), but test both once before relying on them.

## Setup

```bash
pip3 install --user -r requirements.txt
python3 spc_story_generator.py
```

Check `./stories/` for slides (only appears on Enhanced+ days or days with a
hatched tornado area -- to force a test run regardless of current risk,
temporarily add a print of `top_label`/`sig_tornado` and lower the trigger
set, or just test on a day SPC has one of those up).

### One decision you need to make: public or private repo?

This now matters for the **"Download Latest SPC Slides" iOS Shortcut**
(below), not for ntfy -- ntfy only ever sends a text ping, so it doesn't
care about repo visibility:

- **Public repo (or you're fine making just this narrow slice public):**
  the Shortcut can hit `api.github.com` unauthenticated. Given the content
  is just NOAA's own public map data, this is what I'd default to unless
  you have a reason to keep the repo private.
- **Private repo:** the Shortcut's "Get Contents of URL" steps need a
  `Authorization: Bearer <token>` header added (a GitHub personal access
  token with read access to this repo), or the API calls will 404/401.

### Getting slides onto your phone

1. Install the [ntfy app](https://ntfy.sh/) on your phone, subscribe to a
   topic name of your choosing (**treat it like a password** -- ntfy's own
   docs say this explicitly, since there's no sign-up and anyone who knows
   the topic name can subscribe or publish to it).
2. Set it as a repo secret named `SPC_NTFY_TOPIC`.
3. Every run sends **one** text notification, whether or not slides were
   generated ("ENH risk today -- 2 story slide(s) ready in the repo." or a
   "nothing generated" message on a quiet day), so you always know the
   check ran.
4. When slides were generated, run the **"Download Latest SPC Slides"**
   Shortcut (see below) to pull the actual images down, then share straight
   to Instagram Stories.

The `stories` branch and the workflow artifact are both fallbacks if you
ever miss a notification.

### iOS Shortcut: "Download Latest SPC Slides"

Build this in the Shortcuts app to pull the newest set of PNGs straight
from the `stories` branch on demand (no attachments, no ntfy size/expiry
limits -- it just reads the branch). The slide count varies day to day (1
file if no hazard had a probability area, 2 if the hazards slide was also
generated), so this filters by the shared timestamp prefix rather than
assuming a fixed count:

1. **Get Contents of URL** (GET)
   `https://api.github.com/repos/Metamagic-Dev/weather-watcher/contents/stories?ref=stories`
   -- note the `?ref=stories`, since slides live on the `stories` branch,
   not `main`. Returns a JSON array of every file in `stories/`, each with
   a `name` and a `download_url`.
2. **Sort List** -- sort that array by the `name` key, **descending**.
   Filenames encode `spc_story_YYYYMMDD_HHMM_...`, so the newest set sorts
   to the top.
3. **Get Item from List** -- index 1 of the sorted list → **Match Text**
   its `name` against `spc_story_(\d{8}_\d{4})_` → capture Group 1 as
   `LatestStamp`.
4. **Repeat with Each** item in the *full* sorted list (not just the top
   one):
   - **Match Text** the item's `name` against the same
     `spc_story_(\d{8}_\d{4})_` pattern → Group 1 as `ItemStamp`.
   - **If** `ItemStamp` = `LatestStamp`:
     - **Get Dictionary Value** `download_url` on the item.
     - **Get Contents of URL** using that `download_url` -- downloads the
       actual PNG bytes.
     - **Save to Photo Album** (or **Quick Look**, if you'd rather preview
       first).
   - Non-matching items just get skipped -- since the list is sorted
     descending, every match is guaranteed to come before the first
     mismatch, so there's no need for an early exit.
5. Optionally add a **Show Notification** or **Quick Look** at the end so
   you know it finished.

### iOS Shortcut (advanced): trigger a run, wait for it to publish, then download

The Dispatch Workflow action only fires the run -- it doesn't wait for it
or tell you which run it started, so "wait until published" has to be
built as a small polling loop. Shortcuts doesn't have a native "repeat
until" action, so the standard way to do this is a **helper shortcut that
calls itself** every ~15s until a condition is met. Two shortcuts, but
only one you ever run.

**Watch out for:** dispatching only *runs* the workflow -- it doesn't
guarantee new slides, since the script skips publishing (while still
notifying) on days below Enhanced with no hatched tornado area. The design
below also snapshots the `stories` branch listing before and after, so it
can tell the difference between "finished, nothing new" and "finished, here
are your slides" instead of just declaring victory once the run completes.

**Helper shortcut -- "SPC Poll Run"** (receives a Dictionary as Shortcut
Input with keys `before_run_id` and `deadline`; calls itself until done):

1. **Get Dictionary Value** `before_run_id` and `deadline` from Shortcut
   Input.
2. **Get Contents of URL** (GET)
   `https://api.github.com/repos/Metamagic-Dev/weather-watcher/actions/workflows/spc-outlook-story.yml/runs?event=workflow_dispatch&per_page=1`
   -- scoped to this workflow file and to manual (`workflow_dispatch`)
   runs only, so it can't get confused with the cron-scheduled runs.
3. **Get Dictionary Value** `workflow_runs` → **Get Item from List** index 1
   → this is the latest manual run. Pull its `id` and `status` values.
4. **If** that run's `id` equals `before_run_id` (no new run has shown up
   in the API yet) **or** `status` isn't `"completed"`:
   - **Get Current Date** -- if it's past `deadline`, **Stop This
     Shortcut** with output `"timeout"`.
   - Otherwise, **Wait** 15 seconds, then **Run Shortcut** → "SPC Poll
     Run" → passing the *same* Shortcut Input through unchanged, then
     **Stop This Shortcut** with output = that call's result.
5. **Otherwise** (a new run exists and it's completed): **Get Dictionary
   Value** `conclusion` from that run, and **Stop This Shortcut** with
   output = the conclusion (`"success"`, `"failure"`, etc.).

**Main shortcut -- "SPC Publish & Download"** (this is the one you run):

1. **Get Contents of URL** the `stories` branch contents endpoint (same
   URL as the simple Shortcut above, with `?ref=stories`) → **Sort List**
   by `name` descending → **Get Item from List** index 1 → **Get
   Dictionary Value** `name` → save as `BeforeSlideName`.
2. **Get Contents of URL** the same scoped runs endpoint from step 2 above
   → `workflow_runs` → item 1 → `id` → save as `BeforeRunID` (whatever the
   last manual run's ID was, so the poller can recognize a *new* one).
3. **Dispatch Workflow** (your existing action) -- Owner
   `Metamagic-Dev`, Workflow ID `spc-outlook-story.yml`, Repository
   `weather-watcher`, Branch `main` (the workflow file itself still lives
   on `main` -- only the generated slides go to `stories`).
4. **Get Current Date** → add 6 minutes → format as ISO 8601 → save as
   `Deadline`. (6 minutes is generous slack for runner pickup + image
   fetch + git push when the Mac's already awake; bump it up if the Mac
   sometimes needs to wake from sleep first.)
5. **Dictionary**: `{"before_run_id": BeforeRunID, "deadline": Deadline}`
   → **Run Shortcut** → "SPC Poll Run" with this as input → save result as
   `PollResult`.
6. **If** `PollResult` = `"timeout"` → **Show Alert** "Still running after
   6 minutes -- check the Actions tab." → stop.
7. **If** `PollResult` ≠ `"success"` → **Show Alert** "Workflow run failed
   -- check GitHub Actions." → stop.
8. Re-fetch the `stories` branch listing, sort descending, get item 1's
   `name` → `AfterSlideName`. **If** it equals `BeforeSlideName` → **Show
   Alert** "Run finished, but risk didn't reach Enhanced and no hatched
   tornado area -- nothing new to download." → stop.
9. **Otherwise**: same download steps as the simple Shortcut -- the
   stamp-match filter over the freshly-sorted list, **Repeat with Each**
   → get `download_url` → **Get Contents of URL** → **Save to Photo
   Album**.

One more caveat specific to this version: if the Mac's asleep when you
dispatch, the job just sits queued on GitHub's side (self-hosted runners
only pick up jobs while online) -- the 6-minute deadline is a guess for
"runner already awake," not a hard guarantee, so a timeout here doesn't
necessarily mean something's wrong.

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
- Add `SPC_NTFY_TOPIC` as a repository secret.

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
  this workflow only commits on days that trigger (Enhanced+, or a hatched
  tornado area). In a long stretch with neither anywhere in CONUS (more
  plausible in winter), you could still hit 60 quiet days and get
  auto-disabled -- the fix (not yet built)
  would be a separate, infrequent heartbeat commit (e.g. monthly) as a
  backstop, independent of whether any story fired.
- **Push races.** I added `concurrency: cancel-in-progress: false` so
  overlapping scheduled runs queue instead of both trying to push at once,
  but I haven't tested this under real overlap.

**Delivery mechanism**
- The topic name is effectively a password with no rotation/revocation UI
  beyond picking a new one. Don't reuse a topic name you use for anything
  sensitive.
- The "Download Latest SPC Slides" Shortcut hits `api.github.com`
  unauthenticated, which is capped at 60 requests/hour per IP -- a
  non-issue at 5 checks/day, but worth knowing if you run it repeatedly
  while testing.

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
- Auto-detecting hatched significant-severe areas for **hail and wind**
  (`day1otlk_sighail.nolyr.geojson` / `day1otlk_sigwind.nolyr.geojson`
  exist alongside `day1otlk_sigtorn.nolyr.geojson` and follow the same
  `DN=0`/`DN=10` convention) -- only the tornado one is wired in as a
  trigger today.
