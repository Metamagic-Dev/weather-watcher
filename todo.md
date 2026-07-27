# weather-watcher TODO

## Winter weather gap / auto-disable risk (fixed)

~~The scheduled workflow only commits on Enhanced+ severe weather days.~~
Fixed: every run (trigger or not) now pushes a one-line `heartbeat.txt`
timestamp to the `stories` branch, so the 60-day auto-disable clock resets
regardless of weather activity. See "Scheduling via GitHub Actions" in the
README. This replaced the old approach where committing the actual slide
images was what accidentally kept the clock reset -- pictures no longer get
committed to GitHub at all (they're served locally via Cloudflare Tunnel
instead), so the heartbeat had to become its own explicit step.

**Longer-term opportunity:** Winter weather products from SPC/WPC (winter
storm outlooks, ice accumulation forecasts) could be a natural second
feature — story slides for significant snow/ice events would both fill the
content gap and keep the repo active through the quiet severe season. Worth
scoping once the severe weather pipeline is stable.