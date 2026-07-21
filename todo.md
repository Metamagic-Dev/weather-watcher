# weather-watcher TODO

## Winter weather gap / auto-disable risk

The scheduled workflow only commits on Enhanced+ severe weather days. During
a long quiet stretch (most likely late fall through winter), the repo can go
60+ days without a commit and GitHub will auto-disable the schedule with no
alert.

**Short-term fix needed:** Add a separate monthly heartbeat workflow that
makes a trivial commit (e.g. updates a `last-alive.txt`) to reset the timer
regardless of weather activity.

**Longer-term opportunity:** Winter weather products from SPC/WPC (winter
storm outlooks, ice accumulation forecasts) could be a natural second
feature — story slides for significant snow/ice events would both fill the
content gap and keep the repo active through the quiet severe season. Worth
scoping once the severe weather pipeline is stable.