# Drone Map

A live map of drones and missiles over Ukraine, built by reading the public Telegram monitoring
channels (Air Force, reconnaissance channels, regional observers and aggregators) and fusing their
reports into tracks.

- **Every threat type has its own icon:** Shahed, jet Shahed (Geran-3), Gerbera decoy, recon UAV
  (Orlan/ZALA), Lancet, Molniya, FPV, unknown UAV, cruise missile, ballistic missile, Kinzhal,
  unknown missile, guided bomb (KAB). Icons point exactly along the dotted course line drawn for them.
- **Tracks:** reports from different channels are chained into one track per group. Solid lines
  with arrowheads show the flown path, and dotted lines show the reported destination or heading.
  Markers glide to their new position when a report comes in.
- **Correct direction:** the newest report wins (a destination town or a course like "курс
  північно-західний"). Once a target has flown past its reported destination, or reached the region
  it was heading for, the flown path takes over, so an icon never keeps pointing back at a place it
  already passed. The detail panel says where the heading comes from. No speed is shown: post times
  are too coarse to measure one.
- **Heatmap:** where drones (all types), missiles and guided bombs were reported over the last
  **24 hours, 7 days or 28 days**, with a filter for drones, missiles, KABs or explosions. The
  Heatmap tab adds reports per hour or day, a breakdown by type, and the regions and places with the
  most reports (click a place to fly there). History is recorded while Drone Map runs and kept for
  28 days; on start it also reads back the last 24 hours of every channel.
- **Reliability:** each track gets a confidence score from the channels that reported it. Official
  sources weigh most, then reconnaissance, then regional observers. Aggregators only count when they
  agree with someone else, so a target seen only by aggregators is shown faded with a "?".
  Impossible jumps (speed and heading checks), stale targets and shot-down targets are handled.
- **Events:** explosions, shot-down reports, threat areas (e.g. "ballistic threat for Kharkiv
  region"), air-raid alerts per region and nationwide notices (MiG-31K airborne etc.).
- **App:** installable PWA (desktop and phone), works offline with the last known picture, with an
  optional "near me" warning when a confirmed target is close to or heading for your location, and a
  "Follow on map" button that keeps a selected target in view as new reports arrive.

## Run it

Needs Python 3.10+ (on Windows, tick "Add Python to PATH" when installing).

```bash
git clone https://github.com/inasjackw321/drone-map.git
```

```bash
cd drone-map
```

```bash
pip install -r requirements.txt
```

```bash
python run.py
```

Your browser opens the map at http://localhost:8000 (open it yourself if it doesn't). Keep the
terminal window open while you use the map; Ctrl+C stops it. The first full round of channel
reads takes about a minute, and the last 3–4 hours of posts are loaded on start.

To try it without Telegram access, run the built-in scripted scenario:

```bash
python run.py --demo
```

### Install as an app

Open the page in Chrome/Edge (desktop or Android) and press **Install app** in the top bar, or use
the browser menu → *Install*. On iPhone: Share → *Add to Home Screen*. For use outside your own
computer, run it on a server behind HTTPS (service workers and geolocation need HTTPS).

### Docker

```bash
docker compose up -d
```

## How it works

```
Telegram channels ──► scraper (t.me/s/<channel> web preview, or Telethon)
                         │  raw posts → SQLite (data/dronemap.db)
                         ▼
                      parser  (dronemap/parser.py)
                         │  threat type, count, position, destination, origin, heading,
                         │  explosions, shot down, alerts, notices
                         ▼
                      fusion  (dronemap/fusion.py)
                         │  replays the last 4 h in time order → tracks + confidence
                         ▼
                      /api/state ──► web app (web/)
```

* **Sources**: `dronemap/channels.json` lists every channel with its trust tier and region. Edit it
  to add or remove channels. The region tells the parser which villages a channel is likely to
  mean.
* **Places**: `dronemap/gazetteer.py` is a curated list of about 500 cities, towns, regions, seas
  and launch areas, with Ukrainian and Russian spellings and case forms.
  `dronemap/data/settlements.tsv.gz` adds 32,000 villages from GeoNames (it ships with the repo). A village only counts
  when it is capitalised, introduced by a location word ("курсом на", "над", "повз", "→") and
  lies in the channel's region (or a region named in the same post). Rebuild it with
  `scripts/build_settlements.py`.
* **Replay**: the picture is rebuilt from the stored posts every few seconds. That makes it
  deterministic and robust: posts that arrive late or out of order, edited posts and restarts all
  give the same result.
* **Scraper**: each channel is polled on its own schedule (official 20 s, regional 40 s,
  aggregators 75 s), with jitter, a global rate limit, exponential back-off and Retry-After
  handling. Channel health is visible in the **Sources** tab. After the first round it slowly reads
  each channel back 24 hours for the heatmap, at a low rate so live polling keeps priority.
* **Heatmap history**: every observed position (a named town or village, never a region centre) is
  stored in the `heat` table of the same SQLite file with a stable key, so replays never count a
  report twice. Positions are kept for 28 days.

### Optional: Telegram API (Telethon)

A few channels disable the web preview (shown as "no web preview" in the Sources tab). To read
those too, create an API app at https://my.telegram.org, then:

```bash
pip install telethon
```

```bash
TG_API_ID=12345 TG_API_HASH=abc123 python -m dronemap.telethon_login
```

```bash
TG_API_ID=12345 TG_API_HASH=abc123 python run.py --source both
```

`--source both` uses the web preview for everything and the API for channels without a preview;
`--source telethon` uses the API for everything.

### Settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `DRONEMAP_PORT` / `PORT` | `8000` | HTTP port |
| `DRONEMAP_DB` | `data/dronemap.db` | SQLite file for raw posts |
| `DRONEMAP_WINDOW_HOURS` | `4` | how much history is replayed into the picture |
| `DRONEMAP_HISTORY_HOURS` | `24` | how far back each channel is read on start for the heatmap (`0` = off) |
| `DRONEMAP_HEAT_DAYS` | `28` | how long heatmap positions are kept |
| `DRONEMAP_POLL_SCALE` | `1` | multiply all poll intervals (e.g. `2` = half as many requests) |
| `DRONEMAP_SOURCE` | `web` | `web`, `telethon` or `both` |
| `DRONEMAP_CHANNELS` | built-in | path to an alternative channels file |

### API

* `GET /api/state` returns tracks, events, alerts, notices, feed and stats (supports `If-None-Match`)
* `GET /api/heatmap?period=24h|7d|28d&kind=all|drone|missile|kab|explosion` returns heatmap
  cells, reports per hour/day and breakdowns by type, region and place
* `GET /api/sources` returns channels grouped by tier, with health
* `GET /api/health` returns a liveness summary

## Tests

```bash
pip install pytest
```

```bash
python -m pytest
```

Parser rules are tested against message patterns taken from the real channels.

## Limits

This is an aid for situational awareness, built from what public channels post. Positions are as
precise as the posts (often "near village X" or "in region Y"). Reports lag reality by minutes, and
mass missile attacks with dozens of parallel groups can't be separated perfectly from text. Always
follow official air-raid alerts.

## Credits

Map data and tiles © OpenStreetMap contributors (fallback tiles © Esri). Village data © GeoNames (CC BY 4.0).
Map library: Leaflet (BSD-2), heatmap: Leaflet.heat (BSD-2).
