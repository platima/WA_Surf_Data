#!/usr/bin/env python3
"""
capenat_waves.py  (repository: WA_Surf_Data)

Scrapes the WA Department of Transport (DoT) wave buoy chart GIFs for all nine WA stations with live
charts, converts them to numbers by pixel analysis (no general OCR, no ML), and publishes a web page and
JSON, either as a static site on GitHub Pages (via GitHub Actions; see GITHUB PAGES) or from a local web
server. The page shows the station nearest the visitor (see WEB PAGE).
This docstring is the reference for behaviour, limits and calibration; keep it in step with the code.

SOURCE
    Station pages: https://www.transport.wa.gov.au/marine/charts-warnings-current-conditions/
                   coastal-data-charts/wave-data/<slug>
    Stations (STATIONS): geraldton, jurien-bay, cottesloe, rottnest-island, mandurah, cape-naturaliste
                         (default), albany, bremer-bay, esperance. The DoT "Tantabiddi (Exmouth) weather"
                         page has no wave chart GIFs, so it is not included.
    <CODE>_WAVE.GIF  significant wave height (top panel) and mean period (bottom panel), sea/swell/total, 4 days
    <CODE>_POLD.GIF  direction dial: arrow bearing = direction, arrow point radius = peak period, sea and swell
    <CODE>_WDIR.GIF  4-day sea and swell direction history (circles), labelled "From Mag"
    CODE is the station code (DWN Cape Naturaliste, RDW Rottnest Island, DWA Albany, ...). The images live
    at /getmedia/<id>/<CODE>_*.GIF, and the <id> changes between refreshes (a link from 09:56 returned 404
    at 10:30), so the page is read for the current links on every fetch.
    The pages have no JSON or XHR data feed (checked in browser dev tools, 14 Oct 2026); the GIFs are the
    only machine-readable source. DoT publishes quality-controlled archive data (CC BY 3.0 AU) up to the end
    of the previous year, which suits backfill but not live use.
    Station coordinates: DoT "Wave Stations Operational" layer (SLIP DOT-024,
    public-services.slip.wa.gov.au/.../Marine_and_Estuaries/MapServer/14), read 15 Oct 2026. The live
    Bremer Bay and Geraldton buoys are not in that layer; their historic buoy sites (MapServer/15) are used
    and flagged approx_location. Good enough for picking the nearest station, not for navigation.

FILES / ENDPOINTS (same paths on GitHub Pages and the local server)
    index.html               the web page (see WEB PAGE)
    stations.json            {"default": slug, "stations": [{slug, name, lat, lon, approx_location,
                             source_page, has_data, ok, error, chart_time, swell: {height_m, peak_period_s,
                             direction}}]}  north to south, then east
    healthz.json             {"ok", "updated", "failed": [slugs], "stations": {slug: {ok, error, chart_time}}}
                             The local server returns HTTP 503 for it while any station failed; a static host
                             always returns 200, so check "ok".
    <slug>/raw.json          {"status": {...}, "data": {...}}
                  status: ok, last_attempt, last_success, error, etags
                  data.current.swell / .sea : height_m, peak_period_s, mean_period_s, direction_deg,
                                              direction, direction_source ("dial" or "history")
                  data.current.total        : height_m, mean_period_s
                  data.series               : hourly records over the chart window (about 4 days), keys
                                              time, {sea,swell,total}_hs_m, {sea,swell,total}_tm_s,
                                              {sea,swell}_dir_deg
                  data.chart_time           : GIF Last-Modified time (WST)
                  data.latest_point_time    : time of the newest plotted point
                  data.chart_axes           : axis ranges read from the height and period panels, and the
                                              resulting m_per_px / s_per_px (resolution of this chart)
                  data.dial                 : detected dial centre, ring radii and s_per_px (null if not read)
                  data.warnings             : non-fatal problems, e.g. dial not read
                  data.station, station_slug, lat, lon, source_page, notes
    <slug>/history.json      hourly records kept beyond the 4-day window (default 60 days, --history-days)
    <slug>/healthz.json      that station's status object

WEB PAGE
    Shows current swell/sea/total and 4-day height, period and direction charts for one station. Reloads
    stations.json and the station's raw.json every 5 minutes. Times in Australia/Perth (WST, UTC+8, no DST).
    Flags data older than 1.5 h, failed updates and warnings.
    Which station, in order:
      1. URL fragment, e.g. .../#rottnest-island (shareable; not stored).
      2. A station picked in the Location list, kept in localStorage "choice".
      3. "Nearest to me (automatic)", the default: an approximate location from get.geojs.io, falling back
         to ipwho.is, cached in localStorage "geo" for 24 h. If it is in WA (country AU and region "Western
         Australia", or longitude below 129 when no region is given), the nearest station with data is shown.
         Outside WA, it shows Cape Naturaliste with a banner saying so; if both lookups fail, Cape
         Naturaliste with a banner saying the location could not be estimated.
      "Use precise location" asks the browser for the device location (permission prompt), stores it as
      the "geo" estimate and returns to automatic.
    IP-based locations on Australian mobile networks often resolve to a capital city (general knowledge,
    not measured), which is why the automatic choice shows a banner suggesting the precise option.
    The page calls get.geojs.io (and ipwho.is if that fails) from the visitor's browser, which sends those
    services the visitor's IP address; the footer says so. GeoJS states CORS support and "no rate limits
    (yet)" (geojs.io, checked 15 Oct 2026). ipwho.is terms were not checked (its site did not load).
    All localStorage access is wrapped so the page still works when storage is blocked.

REQUIREMENTS AND USAGE
    Python 3.9+, Pillow, numpy:  pip install pillow numpy
    Tested on Linux (Python 3.13); the single-station version also ran on Windows (PowerShell).

    python3 capenat_waves.py --out site            update every station's files in site/ once, exit
                                                   (what the GitHub Actions workflow runs)
    python3 capenat_waves.py                       serve site/ on 0.0.0.0:8080 and update it at :27/:57
    python3 capenat_waves.py --stations cottesloe,rottnest-island --out site    some stations only
    python3 capenat_waves.py --once [--page URL]   fetch one station (default Cape Naturaliste), print JSON
    python3 capenat_waves.py --files WAVE.GIF POLD.GIF WDIR.GIF [--page URL] [--time 2026-10-14T09:56:04+08:00]
                                                   parse saved GIFs, print JSON, exit (for debugging)
    -v enables debug logging.

    --out options: --attempts (default 3) passes, --attempt-wait (default 60) seconds between passes.
    Stations are fetched three at a time; a full run of nine takes about 15 s when DoT responds normally.
    --out exit codes: 0 every station updated or unchanged, 1 any station failed every attempt (files are
    still written, with the error in that station's raw.json and its last good data kept).

    The server keeps --site-dir (default site/) updated and serves it; on start it logs browsable URLs.
    With the default --host 0.0.0.0 (all interfaces, not itself browsable) it lists 127.0.0.1 and the
    machine's LAN address.

SCHEDULE
    DoT regenerates the charts at about :25 and :55 past each hour (observed at Cape Naturaliste; chart
    times across stations on 15 Oct 2026 were :21 to :31). Fetching at :27 and :57 allows for caching.
    Local server: updates at startup and then at --minutes (default 27,57). After a failure it retries
    every --retry minutes (default 5).
    GitHub Actions: cron "27,57 * * * *" in .github/workflows/update.yml (cron minutes are the same in UTC
    and WST).
    Both: a station whose three ETags match the previous fetch is not re-parsed or rewritten.

GITHUB PAGES
    Repository layout:
        capenat_waves.py               this script
        requirements.txt               pillow, numpy
        .github/workflows/update.yml   scheduled job
        site/                          generated files (see FILES), committed by the workflow
    Each run: install dependencies, run "capenat_waves.py --out site", commit site/ if it changed (this
    keeps history between runs, since runners start clean, and counts as repository activity), then
    deploy site/ to Pages. Runs with nothing new skip the commit and deploy. If any station fails every
    attempt, site/ is still committed and deployed so the page shows the error, and the run is then marked
    failed, so GitHub's default notifications email the repo owner. The workflow also runs on manual
    dispatch and when the script, requirements or workflow change on main.

    One-time setup:
      1. Push these files to the main branch of a public repository.
      2. Settings > Pages > Build and deployment > Source: "GitHub Actions".
      3. Actions tab > "Update wave data" > Run workflow. (The push in step 1 also starts a run; if it ran
         before step 2, its Pages steps fail, which is harmless.) The site is then at
         https://<user>.github.io/<repo>/ (also shown on the run's deploy step).
    Action versions (checkout v7, setup-python v7, configure-pages v6, upload-pages-artifact v5,
    deploy-pages v5) were the latest major tags on 15 Oct 2026.

    Caveats:
      - Cost: Actions is free for standard runners in public repositories (GitHub billing docs, checked
        15 Oct 2026). A private repository uses the account's included minutes instead.
      - Timing: GitHub states scheduled runs can be delayed under load, especially at the start of each
        hour, and some may be dropped. Expect the site to lag DoT by more than 2 minutes at times.
      - Auto-disable: GitHub disables scheduled workflows in a public repository after 60 days without
        repository activity. The workflow's own commits are expected to count (inferred, not confirmed);
        if the schedule stops, re-enable it on the Actions tab.
      - DoT may treat GitHub's cloud IP ranges differently from a home connection (untested until the
        first run). A block would show as failed runs and errors on the page.
      - Everything on the site is public, so the licensing note under LIMITS applies.
      - One failing station marks the whole run failed, so a station that stays broken means an email
        every half hour until it is fixed or removed from the workflow with --stations.
      - Repository size grows with every data commit (not measured). Check with "git count-objects -vH"
        on a fresh clone; lowering --history-days in the workflow reduces it.

METHOD
    - Lines, circles and arrows use exact palette colours (no anti-aliasing), so each series is found by
      exact RGB match. WAVE and WDIR use the same colours at every station: sea (0,153,0), swell
      (255,0,0), total (45,90,175). Matching is by RGB, not palette index, because indices vary.
    - Axis scales: DoT auto-scales both WAVE panels per station and over time (seen on 14 Oct 2026: height
      axes topping out at 1.75, 3.5, 4.0, 5.0 and 6.0 m; period axes at 14 and 16 s). Every parse reads the
      right-hand axis labels by exact match against the label font's glyph bitmaps (GLYPHS), snaps each
      label to its gridline row, and fits value = a + b * row. The fit must be linear within 0.75 px.
    - Heights and mean periods: mean y of matching pixels per column, converted with that fit.
      Hourly values are the median of the columns within +/-30 min of each whole hour.
    - Direction history: circular mean of the bearings of all matching circle pixels in each hourly
      window, which handles the N wrap-around (the chart shows N at both top and bottom).
    - Dial (find_dial, parse_polar): the dials differ by station in image size (Esperance 578x490,
      Cottesloe 521x436, others 521x435), centre, spoke colour and arrow colours, and Bremer Bay's legend is
      bottom right. So each parse finds the dial from the image: the spoke colour (POLAR_SPOKE_RGBS) with
      the longest horizontal and vertical lines gives the centre where they cross; a radius histogram of
      that colour, ignoring pixels on the 12 spokes, must show exactly five evenly spaced rings (within
      1.5 px), taken as 4/8/12/16/20 s as labelled on every dial; seconds = a + b * radius is fitted to
      them. Each arrow is the largest 8-connected group of a known arrow colour (POLAR_SEA_RGBS /
      POLAR_SWELL_RGBS) within 1.25x the outer ring radius; bearing from its centroid, peak period from
      its pixel nearest the centre (the point). The arrow colour matches the station's SEA/SWELL legend
      text: sea dark teal at Cape Naturaliste, navy at Cottesloe, green elsewhere; swell mauve at
      Cottesloe, red elsewhere.
    - If the dial cannot be read, the station still updates: peak periods are null, current directions
      come from the newest hourly direction-history value (direction_source "history"), and a warning is
      added to data.warnings and shown on the page.
    - Time axis: midnight gridlines give the scale. The calendar date of the last gridline is chosen so
      the newest point is not later than the GIF's Last-Modified time, which matched the chart's printed
      timestamp (09:56:04 header vs "09:55hrs" on the dial). The newest point is backed off one pixel
      (the end of a ~2 px stroke) and clamped to the file time.

CALIBRATION (measured from the live GIFs on 14 and 15 Oct 2026; constants below)
    WAVE/WDIR size 521x315 at every station.
    Time axis (WAVE and WDIR): frame x 42..485, midnight gridlines x 152/263/374, 111 px per day.
    Height panel: frame rows 27 to 139 (112 px); value scale read from the axis labels each time.
    Mean period panel: frame rows 163 to 276 (113 px); value scale read from the axis labels each time.
    Axis labels: columns 486..520, 8 px high glyphs, ink = mean RGB below 215.
    Direction history: rows 27 (N as 360) to 252 (N as 0), 0.625 px per degree.
    Dial: found per image (see METHOD). Seen on 15 Oct 2026: centre (261,217) and rings at about
    35/69/104/139/174 px at seven stations, (261,218) at Cottesloe, (289,252) with rings 39 to 193 px at
    Esperance.

ACCURACY (from the chart scales, not measured against raw buoy data)
    heights    about +/- one pixel: 0.045 m on a 5 m axis, 0.016 m on a 1.75 m axis, 0.054 m on a 6 m axis
               (data.chart_axes.m_per_px gives the value for the current chart)
    periods    about +/- 0.12 s on a 14 s axis; dial peak periods about +/- 0.12 s (0.10 s at Esperance)
    direction  +/- ~2 deg on the history chart; dial bearings similar (inferred)

VERIFICATION
    14 Oct 2026: the dial prints SEA and SWELL heights as text; these were compared with what the script
    reads from the height chart:
      Cape Naturaliste 09:56   dial 1.65 / 1.04 m   script 1.62 / 1.09 m
      Rottnest Island  10:26   dial 1.12 / 0.90 m   script 1.12 / 0.87 m   (4.0 m axis)
    Before the axis labels were read, Rottnest came out at 1.36 / 1.14 m because a fixed 5.0 m scale was
    assumed. The axis reader was then run on all nine stations' charts; every label was read correctly
    and every fitted zero landed within 0.3 px of the frame line.
    15 Oct 2026, about 06:30 WST, all nine stations (dial text sea / swell vs script sea / swell, m):
      Albany 1.60/1.02 vs 1.63/1.01; Bremer Bay 1.18/1.04 vs 1.20/0.99; Cape Naturaliste 1.39/0.64 vs
      1.32/0.64; Esperance 0.67/0.36 vs 0.63/0.37; Geraldton 0.78/0.69 vs 0.75/0.69; Jurien Bay
      1.06/0.56 vs 1.05/0.62; Mandurah 1.07/0.42 vs 1.02/0.42; Rottnest 1.06/0.61 vs 1.05/0.58;
      Cottesloe 1.07/0.31 vs 1.11/0.21. The Cottesloe swell gap is in DoT's own images: its chart line ends
      at about 0.22 m while its dial (timestamped 06:28) prints 0.31 m. The other gaps (up to 0.07 m) are
      within one to two chart pixels or may reflect the dial and chart not being drawn at the same instant.
      All nine dials were found automatically with five evenly spaced rings. A first version took the
      nearest pixel of the arrow colour as the tip and read Cottesloe's swell as 4.4 s because of stray
      map pixels; the largest-connected-group rule gives 15.4 s, matching the arrow tip by eye.
    Dial arrows at Cape Naturaliste 09:56 on 14 Oct read swell from SW (226 deg) at 12.5 s peak and sea
    from NE (44 deg) at 5.1 s peak, consistent with the direction history.
    Web page, 15 Oct 2026, headless Chromium with the IP lookup faked: Margaret River -> Cape Naturaliste
    (54 km), Perth -> Cottesloe (17 km), Esperance -> Esperance (16 km), Sydney and London -> Cape
    Naturaliste with the outside-WA banner, both lookups failing -> Cape Naturaliste with the "couldn't
    estimate" banner, stored choice -> that station, #geraldton link -> Geraldton, device location at
    Yallingup -> Cape Naturaliste (27 km). No script errors. Rendered at desktop and phone widths, light
    and dark. Not yet tested on a real phone or against the live GeoJS service from an Australian IP.

FAILURE HANDLING
    - Each fetch reads the station page first for the current image links; if the page or an image fails,
      that station's fetch fails and is retried (see SCHEDULE and --attempts).
    - Before parsing, image sizes, frame lines and axis labels are checked; the dial must show spokes and
      five evenly spaced rings. A WAVE or WDIR mismatch raises LayoutError: the station's error is reported
      in its raw.json and healthz.json and its last good data is kept rather than replaced with wrong
      numbers. A dial mismatch only drops the dial values (see METHOD).

LIMITS
    - Current heights come from the end of the height chart, not the text printed on the dial (the dial
      font is not templated). The two can disagree in DoT's own images (Cottesloe, see VERIFICATION).
    - The glyph "9" had not appeared on any axis when GLYPHS was built; it is derived from "6" rotated 180
      degrees. If that is wrong, a chart with a 9 on its axis fails with LayoutError (no wrong numbers) and
      the log prints the glyph bitmap to add to GLYPHS.
    - The dial's outer ring is assumed to be 20 s (true on all nine on 15 Oct 2026). If DoT rescaled the
      dial but kept five evenly spaced rings, peak periods would be wrong without an error.
    - An arrow colour not in POLAR_SEA_RGBS / POLAR_SWELL_RGBS gives null for that arrow's peak period
      (direction then falls back to the history chart). Add the colour from the station's legend text.
    - Where one line hides another, gaps up to 8 px (about 1.7 h) are linearly interpolated; longer
      stretches are null. Hourly direction is null where an hour has fewer than 6 marker pixels.
    - Direction is where waves come from. The history chart is labelled magnetic; the dial is assumed
      to use the same reference (inferred, not confirmed). No declination correction is applied.
    - peak_period_s (dial) and mean_period_s (chart) are different statistics; expect peak > mean.
    - "Nearest" is straight-line distance to the buoy, not to a surf break or along the coast.
    - Licensing: DoT's archive data is CC BY 3.0 AU, but terms for these live charts were not found.
      Check DoT's disclaimer and copyright page before exposing this publicly.
"""

import argparse
import datetime as dt
import io
import json
import logging
import math
import os
import re
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
import time
import urllib.request
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
from PIL import Image

log = logging.getLogger("capenat")

WST = dt.timezone(dt.timedelta(hours=8), "WST")
SITE = "https://www.transport.wa.gov.au"
WAVE_DATA = SITE + "/marine/charts-warnings-current-conditions/coastal-data-charts/wave-data/"
USER_AGENT = "capenat-waves/2.0 (personal surf report; polls twice an hour)"

# Stations with live wave charts, north to south then east. slug = last part of the DoT page URL.
# Coordinates: DoT "Wave Stations Operational" layer (SLIP DOT-024, MapServer/14), read 15 Oct 2026, except
# where approx=True: the live Bremer Bay and Geraldton buoys are not in that layer, so their historic buoy
# sites (MapServer/15: Bremer Bay 02, Geraldton 03) are used. Close enough for choosing the nearest station.
STATIONS = [
    {"slug": "geraldton", "name": "Geraldton", "lat": -28.758876, "lon": 114.535567, "approx": True},
    {"slug": "jurien-bay", "name": "Jurien Bay", "lat": -30.291654, "lon": 114.914455, "approx": False},
    {"slug": "cottesloe", "name": "Cottesloe", "lat": -31.977765, "lon": 115.686678, "approx": False},
    {"slug": "rottnest-island", "name": "Rottnest Island", "lat": -32.094154, "lon": 115.407789, "approx": False},
    {"slug": "mandurah", "name": "Mandurah", "lat": -32.452787, "lon": 115.572227, "approx": False},
    {"slug": "cape-naturaliste", "name": "Cape Naturaliste", "lat": -33.534709, "lon": 114.764455, "approx": False},
    {"slug": "albany", "name": "Albany", "lat": -35.198043, "lon": 117.721955, "approx": False},
    {"slug": "bremer-bay", "name": "Bremer Bay", "lat": -34.423875, "lon": 119.405843, "approx": True},
    {"slug": "esperance", "name": "Esperance", "lat": -34.000542, "lon": 121.90001, "approx": False},
]
for _st in STATIONS:
    _st["page"] = WAVE_DATA + _st["slug"]
STATION_BY_SLUG = {st["slug"]: st for st in STATIONS}
DEFAULT_STATION = "cape-naturaliste"
PAGE_URL = STATION_BY_SLUG[DEFAULT_STATION]["page"]

# ---------------------------------------------------------------------------
# Calibration. Measured from the live GIFs on 14 Oct 2026 (521 x 315 and 521 x 435 px).
# ---------------------------------------------------------------------------
SEA_RGB = (0, 153, 0)
SWELL_RGB = (255, 0, 0)
TOTAL_RGB = (45, 90, 175)
FRAME_RGB = (64, 64, 64)
# Dial colours vary by station (seen across all nine on 15 Oct 2026). The arrow colour matches that
# station's SEA / SWELL legend text: sea is dark teal at Cape Naturaliste, navy at Cottesloe, green elsewhere;
# swell is mauve at Cottesloe, red elsewhere. Spokes and rings are grey, slightly blue-grey at Cottesloe.
POLAR_SEA_RGBS = ((28, 58, 60), (0, 153, 0), (45, 92, 136))
POLAR_SWELL_RGBS = ((255, 0, 0), (158, 122, 136))
POLAR_SPOKE_RGBS = ((128, 128, 128), (123, 135, 139))
POLAR_RING_SECONDS = (4, 8, 12, 16, 20)  # the five rings, inner to outer, as labelled on every dial

# Shared time axis (WAVE and WDIR): frame x 42..485, midnight gridlines at 152, 263, 374.
X_LEFT, X_RIGHT = 42, 485
X_LAST_MIDNIGHT = 374
PX_PER_DAY = 111.0
PX_PER_HOUR = PX_PER_DAY / 24.0

# WAVE panels. The value scales are NOT fixed: DoT auto-scales each axis (seen 1.75 to 6.0 m, 14 and 16 s),
# so values come from reading the right-hand axis labels (read_axis) on every parse.
H_TOP, H_BOT = 27, 139      # height panel frame rows
P_TOP, P_BOT = 163, 276     # mean period panel frame rows
AXIS_X0, AXIS_X1 = 486, 521  # right-hand axis label columns
AXIS_LUM = 215               # pixels darker than this (mean RGB) count as label ink
# Axis label glyphs (8 px high), collected from all nine DoT stations on 14 Oct 2026.
# "9" had not appeared yet; it is derived as "6" rotated 180 degrees (unverified). Unknown glyphs raise LayoutError.
GLYPHS = {
    (".####.", "##....", "#.....", "#####.", "#...#.", "#...##", "##..#.", ".####."): "6",
    ("..", "..", "..", "..", "..", "..", "##", "##"): ".",
    (".###.", "##.##", "#...#", "#...#", "#...#", "#...#", "##.##", ".###."): "0",
    ("#####", "##...", "##...", "#####", "....#", "....#", "#...#", "####."): "5",
    ("....##.", "...###.", "..####.", ".##.##.", "##..##.", "#######", "....##.", "....##."): "4",
    ("#####", "#...#", "...##", ".###.", "....#", "....#", "#...#", "####."): "3",
    ("####..", "#..##.", "....#.", "...##.", "..##..", ".##...", "##....", "######"): "2",
    ("..#..", "###..", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"): "1",
    ("..####.", ".#...#.", ".#...#.", "..###..", ".#...#.", "##...##", ".#...#.", ".#####."): "8",
    ("######", "....#.", "...##.", "...#..", "..##..", "..#...", ".##...", "##...."): "7",
}
GLYPHS[tuple(r[::-1] for r in reversed(next(k for k, v in GLYPHS.items() if v == "6")))] = "9"
# WDIR: frame rows 27 (N, drawn as 360) .. 252 (N, drawn as 0), increasing downwards = decreasing bearing
D_TOP, D_BOT = 27, 252

GRID_RGBS = ((170, 170, 170), (200, 200, 200))  # major and minor gridlines

COMPASS16 = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
             "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


class LayoutError(RuntimeError):
    """The GIF no longer matches the calibrated layout."""


def compass(deg):
    if deg is None:
        return None
    return COMPASS16[int((deg % 360) / 22.5 + 0.5) % 16]


def rnd(v, n):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return round(float(v), n)


def mask(rgb_arr, rgb):
    return np.all(rgb_arr == np.array(rgb, dtype=rgb_arr.dtype), axis=-1)


def load_rgb(blob):
    return np.asarray(Image.open(io.BytesIO(blob)).convert("RGB")).astype(np.int16)


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------
def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        lm = r.headers.get("Last-Modified")
        return r.read(), (parsedate_to_datetime(lm).astimezone(WST) if lm else None), r.headers.get("ETag")


def discover_urls(page_url):
    """Read the page for the current GIF links. DoT's media IDs change between refreshes, so this runs every fetch."""
    html, _, _ = http_get(page_url)
    html = html.decode("utf-8", "replace")
    found = {}
    for m in re.finditer(r'(/getmedia/[0-9a-fA-F-]+/[A-Za-z0-9]+_(WAVE|POLD|WDIR)\.GIF)', html):
        found.setdefault(m.group(2), SITE + m.group(1))
    if len(found) != 3:
        raise RuntimeError(f"could not find all three chart images on {page_url} (found {sorted(found)})")
    return found


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def check_frame(img, rows, name):
    dark = mask(img, FRAME_RGB)
    for y in rows:
        if dark[y, X_LEFT:X_RIGHT + 1].sum() < 400:
            raise LayoutError(f"{name}: expected frame line at row {y}")
    for x in (X_LEFT, X_RIGHT):
        if dark[:, x].sum() < 200:
            raise LayoutError(f"{name}: expected frame line at column {x}")


def column_means(m, y_top, y_bot):
    """Mean y of masked pixels per column inside (y_top, y_bot); NaN where none."""
    sub = m[y_top + 1:y_bot, X_LEFT + 1:X_RIGHT]
    counts = sub.sum(axis=0)
    ys = np.arange(y_top + 1, y_bot)[:, None]
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = (sub * ys).sum(axis=0) / counts
    mean[counts == 0] = np.nan
    return mean


def fill_short_gaps(v, max_gap=8):
    """Linear interpolation across interior gaps up to max_gap columns (lines hidden under other lines)."""
    v = v.copy()
    idx = np.nonzero(~np.isnan(v))[0]
    for a, b in zip(idx[:-1], idx[1:]):
        if 1 < b - a <= max_gap + 1:
            v[a + 1:b] = np.interp(np.arange(a + 1, b), [a, b], [v[a], v[b]])
    return v


def _runs(flags):
    """(start, end) of each run of True values."""
    out, start = [], None
    for i, v in enumerate(list(flags) + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start, i))
            start = None
    return out


def read_axis(img, y0, y1, name):
    """
    Read the right-hand axis labels between rows y0 and y1 and fit value = a + b * row.
    Each label is snapped to the gridline (or frame line) within 2 px of its text centre, because the
    text position is quantised and would otherwise bias values by up to ~1 px.
    Raises LayoutError on an unknown glyph, fewer than 3 labels, or labels that are not evenly spaced.
    """
    ink = img[:, AXIS_X0:AXIS_X1].mean(axis=-1) < AXIS_LUM
    plot = img[:, X_LEFT + 1:X_RIGHT]
    lines = sum(mask(plot, c) for c in GRID_RGBS + (FRAME_RGB,)).sum(axis=1)
    line_rows = np.nonzero(lines > 150)[0]
    rows, values, texts = [], [], []
    for b0, b1 in _runs(ink[y0:y1].any(axis=1)):
        b0, b1 = b0 + y0, b1 + y0
        if b1 - b0 != 8:
            raise LayoutError(f"{name}: axis label band at rows {b0}-{b1} is not 8 px high")
        band = ink[b0:b1]
        text = ""
        for c0, c1 in _runs(band.any(axis=0)):
            key = tuple("".join("#" if v else "." for v in r) for r in band[:, c0:c1])
            if key not in GLYPHS:
                raise LayoutError(f"{name}: unknown axis glyph at row {b0}:\n" + "\n".join(key))
            text += GLYPHS[key]
        try:
            values.append(float(text))
        except ValueError:
            raise LayoutError(f"{name}: unreadable axis label {text!r}") from None
        centre = (b0 + b1 - 1) / 2
        near = line_rows[np.abs(line_rows - centre) <= 2]
        if near.size == 0:
            raise LayoutError(f"{name}: no gridline next to axis label {text!r} at row {centre}")
        rows.append(float(near[np.argmin(np.abs(near - centre))]))
        texts.append(text)
    if len(rows) < 3:
        raise LayoutError(f"{name}: found {len(rows)} axis labels, need at least 3")
    b, a = np.polyfit(rows, values, 1)
    resid = np.abs(np.array(values) - (a + b * np.array(rows))) / abs(b)
    if resid.max() > 0.75:
        raise LayoutError(f"{name}: axis labels {texts} are not evenly spaced (max residual {resid.max():.1f} px)")
    return a, b, texts


def parse_wave(img):
    if img.shape[:2] != (315, 521):
        raise LayoutError(f"WAVE: unexpected size {img.shape[1]}x{img.shape[0]}")
    check_frame(img, (H_TOP, H_BOT, P_TOP, P_BOT), "WAVE")
    ha, hb, hlab = read_axis(img, H_TOP - 9, H_BOT + 9, "WAVE height axis")
    pa, pb, plab = read_axis(img, P_TOP - 9, P_BOT + 9, "WAVE period axis")
    out = {}
    for name, rgb in (("sea", SEA_RGB), ("swell", SWELL_RGB), ("total", TOTAL_RGB)):
        m = mask(img, rgb)
        out[name + "_hs"] = ha + hb * fill_short_gaps(column_means(m, H_TOP, H_BOT))
        out[name + "_tm"] = pa + pb * fill_short_gaps(column_means(m, P_TOP, P_BOT))
    axes = {"height_axis_m": [float(hlab[0]), float(hlab[-1])], "period_axis_s": [float(plab[0]), float(plab[-1])],
            "m_per_px": round(abs(hb), 4), "s_per_px": round(abs(pb), 4)}
    return out, axes  # arrays indexed by column (X_LEFT+1 .. X_RIGHT-1)


def parse_wdir(img):
    if img.shape[:2] != (315, 521):
        raise LayoutError(f"WDIR: unexpected size {img.shape[1]}x{img.shape[0]}")
    check_frame(img, (D_TOP, D_BOT), "WDIR")
    out = {}
    for name, rgb in (("sea", SEA_RGB), ("swell", SWELL_RGB)):
        m = mask(img, rgb)[D_TOP + 1:D_BOT, X_LEFT + 1:X_RIGHT]
        ys = np.arange(D_TOP + 1, D_BOT)[:, None]
        ang = np.radians(360.0 * (D_BOT - ys) / (D_BOT - D_TOP))  # bearing of each row
        out[name] = (m, np.broadcast_to(ang, m.shape))
    return out


def circular_mean_deg(m, ang, c0, c1, min_px=6):
    sub_m = m[:, c0:c1]
    if sub_m.sum() < min_px:
        return None
    a = ang[:, c0:c1][sub_m]
    return math.degrees(math.atan2(np.sin(a).mean(), np.cos(a).mean())) % 360


def find_dial(img):
    """
    Locate the dial in a POLD image. Stations differ in image size, centre, spoke colour and arrow colours,
    so nothing here is fixed. Returns (cx, cy, rings_px, a, b) where seconds = a + b * radius_px.
    """
    best = None
    for rgb in POLAR_SPOKE_RGBS:
        m = mask(img, rgb)
        score = int(m.sum(axis=1).max() + m.sum(axis=0).max())
        if best is None or score > best[0]:
            best = (score, m)
    m = best[1]
    if m.sum(axis=1).max() < 250 or m.sum(axis=0).max() < 250:
        raise LayoutError("POLD: no N-S / E-W spokes found")
    # The longest horizontal and vertical lines are the E-W and N-S spokes; they cross at the centre.
    cy, cx = int(m.sum(axis=1).argmax()), int(m.sum(axis=0).argmax())

    # Ring radii: histogram of spoke-colour pixel distances, ignoring pixels on the 12 spokes (every 30 deg).
    ys, xs = np.nonzero(m)
    rr = np.hypot(xs - cx, ys - cy)
    a30 = np.degrees(np.arctan2(xs - cx, cy - ys)) % 30
    keep = np.minimum(a30, 30 - a30) * np.pi / 180 * rr > 2.5
    h = np.bincount(np.round(rr[keep]).astype(int), minlength=int(rr.max()) + 3)
    h3 = np.convolve(h, [1, 1, 1], "same")
    peaks = [i for i in range(15, len(h) - 1)
             if h3[i] > math.pi * i and h3[i] >= h3[i - 1] and h3[i] >= h3[i + 1]]  # > half a circle of pixels
    groups = []
    for pk in peaks:
        if groups and pk - groups[-1][-1] <= 4:
            groups[-1].append(pk)
        else:
            groups.append([pk])
    rings = [float(np.average(np.arange(g[0] - 1, g[-1] + 2), weights=h[g[0] - 1:g[-1] + 2])) for g in groups]
    if len(rings) != len(POLAR_RING_SECONDS):
        raise LayoutError(f"POLD: expected {len(POLAR_RING_SECONDS)} rings, found {[round(r) for r in rings]}")
    secs = np.array(POLAR_RING_SECONDS, dtype=float)
    b, a = np.polyfit(rings, secs, 1)
    resid_px = np.abs(secs - (a + b * np.array(rings))) / b
    if resid_px.max() > 1.5:
        raise LayoutError(f"POLD: rings {[round(r, 1) for r in rings]} are not evenly spaced")
    return cx, cy, rings, a, b


def largest_component(m):
    """Largest 8-connected group of True pixels in m (as a mask). Arrows are closed outlines, so this drops
    stray pixels of the same colour elsewhere in the map."""
    ys, xs = np.nonzero(m)
    todo = set(zip(ys.tolist(), xs.tolist()))
    best = []
    while todo:
        seed = todo.pop()
        comp, stack = [seed], [seed]
        while stack:
            y, x = stack.pop()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    nb = (y + dy, x + dx)
                    if nb in todo:
                        todo.remove(nb)
                        comp.append(nb)
                        stack.append(nb)
        if len(comp) > len(best):
            best = comp
    out = np.zeros_like(m)
    if best:
        yy, xx = zip(*best)
        out[list(yy), list(xx)] = True
    return out


def parse_polar(img):
    cx, cy, rings, a, b = find_dial(img)
    yy, xx = np.mgrid[:img.shape[0], :img.shape[1]]
    # Arrows can extend past the 20 s ring; 1.25x the outer ring still excludes the legend text.
    in_dial = np.hypot(xx - cx, yy - cy) < rings[-1] * 1.25
    out = {"_dial": {"centre_px": [cx, cy], "rings_px": [round(r, 1) for r in rings], "s_per_px": round(b, 4)}}
    for name, candidates in (("sea", POLAR_SEA_RGBS), ("swell", POLAR_SWELL_RGBS)):
        # whichever known arrow colour has the most pixels inside the dial
        m = max((mask(img, rgb) & in_dial for rgb in candidates), key=lambda mm: int(mm.sum()))
        ys, xs = np.nonzero(largest_component(m))
        if xs.size < 30:
            out[name] = {"peak_period_s": None, "direction_deg": None}
            continue
        r = np.hypot(xs - cx, ys - cy)
        bearing = math.degrees(math.atan2(xs.mean() - cx, cy - ys.mean())) % 360
        out[name] = {"peak_period_s": a + b * r.min(), "direction_deg": bearing}  # arrow point = peak period
    return out


def last_data_column(wave):
    present = ~np.isnan(wave["total_hs"]) | ~np.isnan(wave["swell_hs"])
    idx = np.nonzero(present)[0]
    if idx.size == 0:
        raise LayoutError("WAVE: no data lines found")
    return int(idx[-1])


def resolve_last_midnight(last_col, file_time):
    """Pick the calendar date of the chart's last midnight gridline so the newest point is <= file time."""
    hours_after = (last_col + X_LEFT + 1 - X_LAST_MIDNIGHT) / PX_PER_HOUR
    base = file_time.replace(hour=0, minute=0, second=0, microsecond=0)
    for days_back in (0, 1, 2):
        m = base - dt.timedelta(days=days_back)
        if m + dt.timedelta(hours=hours_after) <= file_time + dt.timedelta(minutes=45):
            return m
    return base


def col_time(col_index, midnight):
    x = col_index + X_LEFT + 1
    return midnight + dt.timedelta(hours=(x - X_LAST_MIDNIGHT) / PX_PER_HOUR)


def station_for_page(page_url):
    slug = page_url.rstrip("/").rsplit("/", 1)[-1]
    if slug in STATION_BY_SLUG:
        return STATION_BY_SLUG[slug]
    return {"slug": slug, "name": slug.replace("-", " ").title(), "lat": None, "lon": None,
            "approx": True, "page": page_url}


def build(wave_img, pold_img, wdir_img, file_time, station):
    wave, axes = parse_wave(wave_img)
    wdir = parse_wdir(wdir_img)
    warnings = []
    try:
        polar = parse_polar(pold_img)
    except LayoutError as e:
        # The dial only adds peak period and the current arrows; carry on without it.
        warnings.append(f"direction dial not read ({e}); peak periods unavailable, directions from history chart")
        polar = {"sea": {"peak_period_s": None, "direction_deg": None},
                 "swell": {"peak_period_s": None, "direction_deg": None}, "_dial": None}

    last_col = last_data_column(wave)
    midnight = resolve_last_midnight(last_col, file_time)
    first_t = col_time(0, midnight)
    # The last column is the far edge of a ~2 px stroke; back off one pixel, and never later than the file.
    last_t = min(col_time(last_col - 1, midnight), file_time)

    # Hourly series: median of the columns within +/-30 min of each whole hour.
    series = []
    t = first_t.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1)
    while t <= last_t:
        cx = (t - midnight).total_seconds() / 3600 * PX_PER_HOUR + X_LAST_MIDNIGHT - X_LEFT - 1
        c0 = max(0, int(math.floor(cx - PX_PER_HOUR / 2)))
        c1 = min(last_col + 1, int(math.ceil(cx + PX_PER_HOUR / 2)) + 1)
        rec = {"time": t.isoformat()}
        for k, arr in wave.items():
            seg = arr[c0:c1]
            seg = seg[~np.isnan(seg)]
            rec[k + ("_m" if k.endswith("_hs") else "_s")] = rnd(np.median(seg), 2) if seg.size else None
        for name in ("sea", "swell"):
            m, ang = wdir[name]
            rec[name + "_dir_deg"] = rnd(circular_mean_deg(m, ang, c0, c1), 0)
        series.append(rec)
        t += dt.timedelta(hours=1)

    # Latest values: last two data columns (about 25 minutes) for heights and mean periods.
    latest = {}
    for k, arr in wave.items():
        seg = arr[max(0, last_col - 1):last_col + 1]
        seg = seg[~np.isnan(seg)]
        latest[k] = float(seg.mean()) if seg.size else None

    def comp(name):
        p = polar[name]
        d, src = p["direction_deg"], "dial"
        if d is None:  # fall back to the newest hourly value from the direction history chart
            d = next((r[name + "_dir_deg"] for r in reversed(series[-2:]) if r[name + "_dir_deg"] is not None), None)
            src = "history" if d is not None else None
        return {
            "height_m": rnd(latest[name + "_hs"], 2),
            "peak_period_s": rnd(p["peak_period_s"], 1),
            "mean_period_s": rnd(latest[name + "_tm"], 1),
            "direction_deg": rnd(d, 0),
            "direction": compass(d),
            "direction_source": src,
        }

    return {
        "station": station["name"],
        "station_slug": station["slug"],
        "lat": station["lat"],
        "lon": station["lon"],
        "source": "WA Department of Transport wave buoy charts",
        "source_page": station["page"],
        "chart_time": file_time.isoformat(),
        "latest_point_time": last_t.isoformat(),
        "chart_axes": axes,
        "dial": polar["_dial"],
        "warnings": warnings,
        "current": {
            "swell": comp("swell"),
            "sea": comp("sea"),
            "total": {"height_m": rnd(latest["total_hs"], 2), "mean_period_s": rnd(latest["total_tm"], 1)},
        },
        "series": series,
        "notes": {
            "method": "Values read from chart pixels, not from a data feed.",
            "accuracy": "About one pixel: see chart_axes.m_per_px and s_per_px; direction about +/-2 deg.",
            "direction": "Direction waves come from, in degrees. The DoT history chart is labelled magnetic; "
                         "the current arrows are assumed to be the same.",
            "periods": "peak_period_s comes from the direction dial arrows, mean_period_s from the mean period chart.",
            "gaps": "Null where a line is hidden behind another for more than ~1.7 h, or no direction marker exists.",
        },
    }


# ---------------------------------------------------------------------------
# Per-station state and fetching
# ---------------------------------------------------------------------------
class Store:
    """State for one station: last data, status, ETags and the hourly history file."""

    def __init__(self, history_path, history_days):
        self.lock = threading.Lock()
        self.data = None
        self.status = {"ok": False, "last_attempt": None, "last_success": None, "error": "not fetched yet"}
        self.etags = {}
        self.history_path = history_path
        self.history_days = history_days
        self.history = {}
        if history_path and os.path.exists(history_path):
            try:
                with open(history_path) as f:
                    self.history = {r["time"]: r for r in json.load(f)}
            except Exception as e:  # noqa: BLE001
                log.warning("could not read history %s: %s", history_path, e)

    def merge_history(self, series):
        for r in series:
            self.history[r["time"]] = r
        cutoff = (dt.datetime.now(WST) - dt.timedelta(days=self.history_days)).isoformat()
        self.history = {k: v for k, v in self.history.items() if k >= cutoff}


def fetch_and_parse(store, station):
    """Fetch and parse one station. Returns "updated", "unchanged" (same ETags as last time) or "failed"."""
    now = dt.datetime.now(WST)
    name = station["name"]
    try:
        urls = discover_urls(station["page"])  # media IDs rotate, so always read the current links first
        blobs = {k: http_get(u) for k, u in urls.items()}

        etags = {k: b[2] for k, b in blobs.items()}
        if store.data is not None and all(etags[k] and etags[k] == store.etags.get(k) for k in etags):
            log.info("%s: charts unchanged since last fetch", name)
            with store.lock:
                store.status.update(last_attempt=now.isoformat(), ok=True, error=None)
            return "unchanged"

        file_time = blobs["POLD"][1] or blobs["WAVE"][1] or now
        data = build(load_rgb(blobs["WAVE"][0]), load_rgb(blobs["POLD"][0]), load_rgb(blobs["WDIR"][0]),
                     file_time, station)
        with store.lock:
            store.data = data
            store.etags = etags
            store.status.update(ok=True, last_attempt=now.isoformat(), last_success=now.isoformat(), error=None,
                                etags=etags)
            store.merge_history(data["series"])
        c = data["current"]
        log.info("%s: swell %s m %s s %s, sea %s m %s s %s, chart time %s%s", name,
                 c["swell"]["height_m"], c["swell"]["peak_period_s"], c["swell"]["direction"],
                 c["sea"]["height_m"], c["sea"]["peak_period_s"], c["sea"]["direction"], data["chart_time"],
                 "".join(f"; WARNING {w}" for w in data["warnings"]))
        return "updated"
    except Exception as e:  # noqa: BLE001
        log.error("%s: update failed: %s: %s", name, type(e).__name__, e)
        log.debug("traceback", exc_info=True)
        with store.lock:
            store.status.update(ok=False, last_attempt=now.isoformat(), error=f"{type(e).__name__}: {e}")
        return "failed"


# ---------------------------------------------------------------------------
# Site files (used by both GitHub Pages and the local server)
# ---------------------------------------------------------------------------
def _write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, separators=(",", ":"))
    os.replace(tmp, path)


def _load_store(out_dir, slug, history_days):
    sdir = os.path.join(out_dir, slug)
    store = Store(os.path.join(sdir, "history.json"), history_days)
    try:
        with open(os.path.join(sdir, "raw.json"), encoding="utf-8") as f:
            prev = json.load(f)
        store.data = prev.get("data")
        store.status.update(prev.get("status") or {})
        store.etags = store.status.get("etags") or {}
    except FileNotFoundError:
        pass
    except Exception as e:  # noqa: BLE001
        log.warning("%s: could not read previous raw.json: %s", slug, e)
    return store


def _summary(store, station):
    d = store.data or {}
    cur = d.get("current") or {}
    sw = cur.get("swell") or {}
    return {
        "slug": station["slug"], "name": station["name"], "lat": station["lat"], "lon": station["lon"],
        "approx_location": station["approx"], "source_page": station["page"],
        "has_data": bool(d), "ok": store.status.get("ok"), "error": store.status.get("error"),
        "chart_time": d.get("chart_time"),
        "swell": {k: sw.get(k) for k in ("height_m", "peak_period_s", "direction")} if sw else None,
    }


def update_site(out_dir, slugs, history_days, attempts=3, attempt_wait=60, workers=3):
    """
    One update of every station in slugs. Per station, reads the previous raw.json / history.json from
    out_dir/<slug>/ (so state survives between CI runs), fetches, and rewrites that station's files unless
    its charts are unchanged. Failed stations are retried together after attempt_wait seconds.
    Then writes index.html, stations.json and healthz.json. Returns 0, or 1 if any station failed.
    """
    os.makedirs(out_dir, exist_ok=True)
    stores = {slug: _load_store(out_dir, slug, history_days) for slug in slugs}
    results, pending = {}, list(slugs)
    for i in range(max(1, attempts)):
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for slug, res in zip(pending, ex.map(lambda sl: fetch_and_parse(stores[sl], STATION_BY_SLUG[sl]),
                                                  pending)):
                results[slug] = res
        pending = [sl for sl in pending if results[sl] == "failed"]
        if not pending or i + 1 >= attempts:
            break
        log.info("retrying %s in %d s (attempt %d of %d)", ", ".join(pending), attempt_wait, i + 2, attempts)
        time.sleep(attempt_wait)

    for slug in slugs:
        store, sdir = stores[slug], os.path.join(out_dir, slug)
        if results[slug] == "unchanged" and os.path.exists(os.path.join(sdir, "raw.json")):
            continue
        os.makedirs(sdir, exist_ok=True)
        _write_json(os.path.join(sdir, "raw.json"), {"status": store.status, "data": store.data})
        _write_json(os.path.join(sdir, "healthz.json"), store.status)
        _write_json(os.path.join(sdir, "history.json"), [store.history[k] for k in sorted(store.history)])

    # Site-level files. stations.json lists every known station, including ones not fetched this run.
    listed = []
    for st in STATIONS:
        store = stores.get(st["slug"]) or _load_store(out_dir, st["slug"], history_days)
        listed.append(_summary(store, st))
    _write_json(os.path.join(out_dir, "stations.json"), {"default": DEFAULT_STATION, "stations": listed})
    failed = sorted(sl for sl, r in results.items() if r == "failed")
    _write_json(os.path.join(out_dir, "healthz.json"), {
        "ok": not failed, "updated": dt.datetime.now(WST).isoformat(), "failed": failed,
        "stations": {s["slug"]: {"ok": s["ok"], "error": s["error"], "chart_time": s["chart_time"]} for s in listed},
    })
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(PAGE)
    counts = {r: sum(1 for v in results.values() if v == r) for r in ("updated", "unchanged", "failed")}
    log.info("site %s: %d updated, %d unchanged, %d failed%s", out_dir, counts["updated"], counts["unchanged"],
             counts["failed"], f" ({', '.join(failed)})" if failed else "")
    return 1 if failed else 0


def next_run(now, minutes):
    for add_h in (0, 1):
        for m in sorted(minutes):
            t = now.replace(minute=m, second=0, microsecond=0) + dt.timedelta(hours=add_h)
            if t > now:
                return t
    return now + dt.timedelta(minutes=30)


def scheduler(site_dir, slugs, history_days, minutes, retry_min):
    while True:
        try:
            rc = update_site(site_dir, slugs, history_days, attempts=1)
        except Exception:  # noqa: BLE001
            log.exception("site update crashed")
            rc = 1
        now = dt.datetime.now(WST)
        t = next_run(now, minutes)
        if rc:
            t = min(t, now + dt.timedelta(minutes=retry_min))
        time.sleep(max(1.0, (t - now).total_seconds()))


# ---------------------------------------------------------------------------
# Web page
# ---------------------------------------------------------------------------
PAGE = r"""<!doctype html>
<html lang="en-AU"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WA Wave Buoys</title>
<style>
:root{--bg:#f6f5f1;--card:#fff;--fg:#1d2327;--muted:#66707a;--line:#d9dcdf;--note:#eef3fa;--noteline:#c9d7ea;
--swell:#d33a2c;--sea:#1f8a3a;--total:#2d5aaf}
@media (prefers-color-scheme:dark){:root{--bg:#121619;--card:#1b2126;--fg:#e8ecef;--muted:#93a0ab;--line:#2c343b;
--note:#1c2733;--noteline:#2e4257;--swell:#ff6b5c;--sea:#4cc16a;--total:#6f9bf0}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.4 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:900px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:4px 0 2px}.sub{color:var(--muted);font-size:13px;margin-bottom:12px}
.picker{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 12px}
.picker label{font-size:13px;color:var(--muted)}
select,button{font:inherit;font-size:14px;color:var(--fg);background:var(--card);border:1px solid var(--line);
border-radius:8px;padding:6px 10px;max-width:100%}
button{cursor:pointer}button:hover,select:hover{border-color:var(--muted)}
.banner{background:var(--note);border:1px solid var(--noteline);border-radius:10px;padding:10px 12px;margin:0 0 12px;font-size:14px}
.banner[hidden]{display:none}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;display:flex;gap:14px;align-items:center}
.card h2{margin:0 0 4px;font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.big{font-size:30px;font-weight:650;font-variant-numeric:tabular-nums}
.big small{font-size:16px;font-weight:500;color:var(--muted)}
.det{color:var(--muted);font-size:13px;font-variant-numeric:tabular-nums}
.dial{flex:0 0 64px;height:64px}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 12px 4px;margin-top:12px}
section h3{margin:0 0 6px;font-size:14px}
svg.chart{width:100%;height:auto;display:block}
.leg span{margin-right:12px;font-size:12px;color:var(--muted)}.leg i{display:inline-block;width:10px;height:3px;margin-right:4px;vertical-align:middle}
.err{color:var(--swell);font-size:13px}
footer{color:var(--muted);font-size:12px;margin:14px 0}footer p{margin:0 0 6px}
a{color:inherit}
</style></head><body><main>
<h1 id="title">WA wave buoys</h1>
<div class="sub" id="sub">Loading…</div>
<div class="picker"><label for="loc">Location</label><select id="loc"></select>
<button id="gps" type="button">Use precise location</button></div>
<div class="banner" id="banner" hidden></div>
<div class="cards" id="cards"></div>
<section><h3>Significant wave height (m)</h3><div class="leg" id="leg1"></div><svg class="chart" id="ch"></svg></section>
<section><h3>Mean period (s)</h3><div class="leg" id="leg2"></div><svg class="chart" id="cp"></svg></section>
<section><h3>Direction from (°)</h3><div class="leg" id="leg3"></div><svg class="chart" id="cd"></svg></section>
<footer>
<p>Read from WA Department of Transport chart images by pixel analysis. Accuracy is about one chart pixel
(<span id="acc">see raw.json</span>), direction about ±2°. Directions per the DoT charts (labelled magnetic).
Source: <a id="src" href="#">transport.wa.gov.au</a>. Data: <a id="rawlink" href="#">raw.json</a>,
<a id="histlink" href="#">history.json</a>, <a href="stations.json">stations.json</a>.</p>
<p>"Nearest to me" estimates your location from your IP address via get.geojs.io (ipwho.is as a fallback),
or from your device if you press "Use precise location". Your choice and that estimate are kept only in
this browser.</p>
</footer>
</main>
<script>
const C=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const fmt=(v,d)=>v==null?"–":v.toFixed(d);
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const TZ='Australia/Perth',DAY=86400000,OFF=8*3600000,GEO_MAX_AGE=DAY;
const store={get(k){try{return JSON.parse(localStorage.getItem(k))}catch(e){return null}},
  set(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch(e){}}};
let STATIONS=[],DEFAULT="cape-naturaliste",CURRENT=null;

function dial(deg,col){
  if(deg==null)return '<svg class="dial" viewBox="-32 -32 64 64"></svg>';
  // arrow points the way the waves travel (from 'deg' towards the opposite side)
  return `<svg class="dial" viewBox="-32 -32 64 64"><circle r="29" fill="none" stroke="${C('--line')}" stroke-width="2"/>
  <text y="-19" text-anchor="middle" font-size="9" fill="${C('--muted')}">N</text>
  <g transform="rotate(${deg})"><line y1="-24" y2="16" stroke="${col}" stroke-width="3"/>
  <path d="M0 24 L-7 12 L7 12Z" fill="${col}"/></g></svg>`;
}
function card(title,c,col){
  const per=c.peak_period_s!=null?`${fmt(c.peak_period_s,1)}<small> s</small>`:"";
  const bits=[];
  if(c.direction)bits.push(`from ${c.direction} (${c.direction_deg}°)`);
  if(c.mean_period_s!=null)bits.push(`mean ${fmt(c.mean_period_s,1)} s`);
  return `<div class="card">${dial(c.direction_deg,col)}<div><h2 style="color:${col}">${title}</h2>
  <div class="big">${fmt(c.height_m,1)}<small> m</small> ${per}</div>
  <div class="det">${bits.join(" · ")}</div></div></div>`;
}
function chart(id,series,keys,opt){
  const el=document.getElementById(id);
  const W=Math.max(300,Math.round(el.parentElement.clientWidth-24)),H=opt.h||170,L=34,R=8,T=8,B=22;
  if(!series.length){el.innerHTML="";return}
  const t0=Date.parse(series[0].time),t1=Date.parse(series[series.length-1].time);
  const X=t=>L+(W-L-R)*(t-t0)/Math.max(1,t1-t0);
  let ymax=opt.max,ticks=opt.ticks;
  if(ymax==null){const hi=Math.max(0.5,...series.flatMap(r=>keys.map(k=>r[k[0]]??0)));
    const step=hi<=2?0.5:1;ymax=Math.ceil(hi*1.05/step)*step;ticks=[];for(let v=0;v<=ymax+1e-9;v+=step)ticks.push(v)}
  const Y=v=>T+(H-T-B)*(1-v/ymax);
  let s=`<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" xmlns="http://www.w3.org/2000/svg">`;
  for(const v of ticks){s+=`<line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" stroke="${C('--line')}"/>
   <text x="${L-5}" y="${Y(v)+4}" text-anchor="end" font-size="11" fill="${C('--muted')}">${opt.lab?opt.lab(v):(ymax<=3?v.toFixed(1):v)}</text>`}
  // day boundaries at Perth midnight (UTC+8, no DST), labelled with the day that starts there
  const short=W<560;
  for(let d=Math.ceil((t0+OFF)/DAY)*DAY-OFF;d<=t1;d+=DAY){const x=X(d);
   s+=`<line x1="${x}" x2="${x}" y1="${T}" y2="${H-B}" stroke="${C('--line')}"/>`;
   if(x<W-R-(short?34:70))s+=`<text x="${x+3}" y="${H-6}" font-size="11" fill="${C('--muted')}">${new Date(d).toLocaleDateString('en-AU',
     short?{timeZone:TZ,weekday:'short'}:{timeZone:TZ,weekday:'short',day:'numeric',month:'short'})}</text>`}
  for(const [k,col] of keys){
    if(opt.dots){for(const r of series)if(r[k]!=null)s+=`<circle cx="${X(Date.parse(r.time))}" cy="${Y(r[k])}" r="2.6" fill="${col}"/>`;continue}
    let p="",pen=false;
    for(const r of series){const v=r[k];if(v==null){pen=false;continue}
      p+=(pen?"L":"M")+X(Date.parse(r.time)).toFixed(1)+" "+Y(v).toFixed(1)+" ";pen=true}
    s+=`<path d="${p}" fill="none" stroke="${col}" stroke-width="2" stroke-linejoin="round"/>`;
  }
  el.outerHTML=s.replace("<svg ",`<svg id="${id}" class="chart" `)+"</svg>";
}
function legend(id,items){document.getElementById(id).innerHTML=items.map(([n,c])=>`<span><i style="background:${c}"></i>${n}</span>`).join("")}

// ---- location ----
function km(a,b,c,d){const r=Math.PI/180,x=Math.sin((c-a)*r/2)**2+Math.cos(a*r)*Math.cos(c*r)*Math.sin((d-b)*r/2)**2;return 12742*Math.asin(Math.sqrt(x))}
function inWA(g){
  if(g.src==="gps")return g.lat<-13&&g.lat>-36&&g.lon>112&&g.lon<129;
  if(g.cc!=="AU")return false;
  if(g.region)return /western australia/i.test(g.region);
  return g.lon<129;  // WA's eastern border is the 129th meridian
}
async function getJSON(url,ms){
  const c=new AbortController(),t=setTimeout(()=>c.abort(),ms);
  try{const r=await fetch(url,{signal:c.signal,cache:"no-store"});if(!r.ok)throw new Error(r.status);return await r.json()}
  finally{clearTimeout(t)}
}
async function ipGeo(){
  const cached=store.get("geo");
  if(cached&&Date.now()-cached.t<GEO_MAX_AGE)return cached;
  let g=null;
  try{const j=await getJSON("https://get.geojs.io/v1/ip/geo.json",4000);
    if(j.latitude)g={lat:+j.latitude,lon:+j.longitude,cc:j.country_code,region:j.region||"",src:"ip"}}catch(e){}
  if(!g)try{const j=await getJSON("https://ipwho.is/",4000);
    if(j.success!==false&&j.latitude!=null)g={lat:+j.latitude,lon:+j.longitude,cc:j.country_code,region:j.region||"",src:"ip"}}catch(e){}
  if(g){g.t=Date.now();store.set("geo",g)}
  return g;
}
function nearest(g){
  let best=null;
  for(const s of STATIONS){if(!s.has_data||s.lat==null)continue;
    const d=km(g.lat,g.lon,s.lat,s.lon);if(!best||d<best.d)best={s,d}}
  return best;
}
function setBanner(html){const b=document.getElementById("banner");b.innerHTML=html||"";b.hidden=!html}

async function resolveStation(){
  const hash=decodeURIComponent(location.hash.slice(1));
  if(STATIONS.some(s=>s.slug===hash))return {slug:hash,why:"link"};
  const choice=store.get("choice")||"auto";
  if(choice!=="auto"&&STATIONS.some(s=>s.slug===choice))return {slug:choice,why:"chosen"};
  const g=await ipGeo();
  if(!g)return {slug:DEFAULT,why:"nogeo"};
  if(!inWA(g))return {slug:DEFAULT,why:"outside",g};
  const n=nearest(g);
  return n?{slug:n.s.slug,why:"nearest",g,d:n.d}:{slug:DEFAULT,why:"nogeo"};
}
function explain(r){
  const name=(STATIONS.find(s=>s.slug===r.slug)||{}).name||r.slug;
  if(r.why==="nearest")return {sub:`Nearest buoy to you, about ${Math.round(r.d)} km away (${r.g.src==="gps"?"device location":"estimated from your IP address"})`,
    banner:r.g.src==="ip"?`Showing <b>${esc(name)}</b>, the nearest buoy to your approximate location. IP-based locations can be off by a long way, especially on mobile data; use <b>Use precise location</b> or pick a location if this is wrong.`:""};
  if(r.why==="outside")return {sub:"Default location",
    banner:`You appear to be outside Western Australia, so this shows <b>${esc(name)}</b>. Pick another location above if you like.`};
  if(r.why==="nogeo")return {sub:"Default location",
    banner:`Couldn't estimate your location, so this shows <b>${esc(name)}</b>. Pick another location above.`};
  if(r.why==="link")return {sub:"Location from the page link",banner:""};
  return {sub:"Your chosen location",banner:""};
}
function fillPicker(sel){
  const el=document.getElementById("loc");
  const opt=(v,t)=>`<option value="${esc(v)}">${esc(t)}</option>`;
  el.innerHTML=opt("auto","Nearest to me (automatic)")+STATIONS.map(s=>{
    const w=s.swell,t=!s.has_data?" (no data)":w&&w.height_m!=null?` · swell ${fmt(w.height_m,1)} m${w.peak_period_s!=null?" "+Math.round(w.peak_period_s)+" s":""}`:"";
    return opt(s.slug,s.name+t)}).join("");
  el.value=sel;
}

// ---- data ----
async function showStation(slug,info){
  CURRENT=slug;
  const st=STATIONS.find(s=>s.slug===slug)||{name:slug};
  document.getElementById("rawlink").href=`${slug}/raw.json`;
  document.getElementById("histlink").href=`${slug}/history.json`;
  let j;
  try{j=await getJSON(`${slug}/raw.json`,10000)}catch(e){
    document.getElementById("sub").innerHTML=`<span class="err">Could not load ${esc(slug)}/raw.json: ${esc(e)}</span>`;return}
  const title=document.getElementById("title");title.textContent=`${st.name} wave buoy`;document.title=`${st.name} Swell`;
  if(!j.data){document.getElementById("sub").innerHTML=`<span class="err">No data yet for ${esc(st.name)}: ${esc(j.status.error||"")}</span>`;
    document.getElementById("cards").innerHTML="";return}
  const d=j.data,c=d.current,sw=C('--swell'),se=C('--sea'),to=C('--total');
  const t=new Date(d.chart_time),ageH=(Date.now()-t)/3600000;
  document.getElementById("sub").innerHTML=esc(info.sub)+` · chart time ${t.toLocaleString('en-AU',{timeZone:TZ,weekday:'short',hour:'2-digit',minute:'2-digit',day:'numeric',month:'short'})} WST`+
    (ageH>1.5?` · <span class="err">${ageH.toFixed(1)} h old</span>`:"")+
    (j.status.ok?"":` · <span class="err">last update failed: ${esc(j.status.error)}</span>`)+
    ((d.warnings||[]).length?` · <span class="err">${esc(d.warnings.join("; "))}</span>`:"");
  document.getElementById("src").href=d.source_page;
  document.getElementById("acc").textContent=`±${d.chart_axes.m_per_px.toFixed(2)} m, ±${d.chart_axes.s_per_px.toFixed(2)} s on this chart`;
  document.getElementById("cards").innerHTML=card("Swell",c.swell,sw)+card("Sea (wind waves)",c.sea,se)+
    card("Total",{height_m:c.total.height_m,mean_period_s:c.total.mean_period_s},to);
  const S=d.series,ks=[["Swell",sw],["Sea",se]],kt=[...ks,["Total",to]];
  legend("leg1",kt);legend("leg2",kt);legend("leg3",ks);
  chart("ch",S,[["swell_hs_m",sw],["sea_hs_m",se],["total_hs_m",to]],{});
  const pmax=Math.max(16,Math.ceil(Math.max(...S.flatMap(r=>[r.swell_tm_s||0,r.total_tm_s||0]))/4)*4);
  chart("cp",S,[["swell_tm_s",sw],["sea_tm_s",se],["total_tm_s",to]],{max:pmax,ticks:Array.from({length:pmax/4+1},(_,i)=>i*4),lab:v=>v});
  const nm={0:"N",90:"E",180:"S",270:"W",360:"N"};
  chart("cd",S,[["swell_dir_deg",sw],["sea_dir_deg",se]],{max:360,dots:true,h:190,ticks:[0,90,180,270,360],lab:v=>nm[v]});
}
async function refresh(){
  try{const j=await getJSON("stations.json",10000);STATIONS=j.stations;DEFAULT=j.default||DEFAULT}
  catch(e){document.getElementById("sub").innerHTML=`<span class="err">Could not load stations.json: ${esc(e)}</span>`;return}
  const r=await resolveStation();
  const choice=location.hash.slice(1)&&r.why==="link"?r.slug:(store.get("choice")||"auto");
  fillPicker(STATIONS.some(s=>s.slug===choice)?choice:"auto");
  const info=explain(r);setBanner(info.banner);
  await showStation(r.slug,info);
}
document.getElementById("loc").addEventListener("change",e=>{
  const v=e.target.value;store.set("choice",v);
  history.replaceState(null,"",v==="auto"?location.pathname+location.search:"#"+v);
  refresh();
});
document.getElementById("gps").addEventListener("click",()=>{
  if(!navigator.geolocation){setBanner("This browser can't provide a device location.");return}
  setBanner("Getting your location…");
  navigator.geolocation.getCurrentPosition(p=>{
    store.set("geo",{lat:p.coords.latitude,lon:p.coords.longitude,src:"gps",t:Date.now()});
    store.set("choice","auto");history.replaceState(null,"",location.pathname+location.search);refresh();
  },err=>setBanner(`Couldn't get your device location (${esc(err.message||err.code)}).`),
  {enableHighAccuracy:false,timeout:15000,maximumAge:600000});
});
addEventListener("hashchange",refresh);
refresh();setInterval(refresh,5*60*1000);
let rz;addEventListener("resize",()=>{clearTimeout(rz);rz=setTimeout(()=>{if(CURRENT)refresh()},250)});
</script></body></html>"""


# ---------------------------------------------------------------------------
# Local server: serves the site directory and keeps it updated
# ---------------------------------------------------------------------------
def browse_urls(host, port):
    """URLs a person can actually open. 0.0.0.0 / :: mean "all interfaces" and are not browsable."""
    if host not in ("0.0.0.0", "::", ""):
        return [f"http://{host}:{port}"]
    out = [f"http://127.0.0.1:{port}"]
    try:  # LAN address of the default route; UDP connect sends no packets
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
            sk.connect(("192.0.2.1", 9))
            ip = sk.getsockname()[0]
        if not ip.startswith("127."):
            out.append(f"http://{ip}:{port}")
    except OSError:
        pass
    return out


CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".json": "application/json"}


def make_handler(site_dir):
    root = os.path.realpath(site_dir)

    class H(BaseHTTPRequestHandler):
        server_version = "capenat-waves/2.0"

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            rel = urllib.request.url2pathname(self.path.split("?", 1)[0].split("#", 1)[0]).lstrip("/\\")
            if rel in ("", "healthz"):
                rel = rel and "healthz.json" or "index.html"
            path = os.path.realpath(os.path.join(root, rel))
            if not path.startswith(root + os.sep) or not os.path.isfile(path):
                return self._send(404, b"not found\n", "text/plain")
            with open(path, "rb") as f:
                body = f.read()
            code = 200
            if os.path.basename(path) == "healthz.json":
                try:
                    code = 200 if json.loads(body).get("ok") else 503
                except ValueError:
                    code = 503
            self._send(code, body, CONTENT_TYPES.get(os.path.splitext(path)[1], "application/octet-stream"))

        def log_message(self, fmt, *args):
            log.debug("%s %s", self.address_string(), fmt % args)

    return H


def parse_station_list(text):
    if not text or text == "all":
        return [st["slug"] for st in STATIONS]
    slugs = [x.strip() for x in text.split(",") if x.strip()]
    unknown = [x for x in slugs if x not in STATION_BY_SLUG]
    if unknown:
        raise SystemExit(f"unknown station(s): {', '.join(unknown)}; known: {', '.join(STATION_BY_SLUG)}")
    return slugs


def main():
    ap = argparse.ArgumentParser(description="WA DoT wave buoy charts to JSON and a web page")
    ap.add_argument("--out", metavar="DIR",
                    help="update the site files in DIR once and exit (what GitHub Actions runs)")
    ap.add_argument("--site-dir", default="site", help="server mode: directory to keep updated and serve")
    ap.add_argument("--stations", default="all", help="comma-separated station slugs (default: all)")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--minutes", default="27,57",
                    help="server mode: minutes past the hour to update (DoT refreshes at :25 and :55)")
    ap.add_argument("--retry", type=int, default=5, help="server mode: minutes between retries after a failure")
    ap.add_argument("--attempts", type=int, default=3, help="--out mode: fetch attempts per station")
    ap.add_argument("--attempt-wait", type=int, default=60, help="--out mode: seconds between attempts")
    ap.add_argument("--history-days", type=int, default=60)
    ap.add_argument("--page", default=PAGE_URL, help="--once / --files: DoT station page (default Cape Naturaliste)")
    ap.add_argument("--once", action="store_true", help="fetch one station (--page) once, print JSON, exit")
    ap.add_argument("--files", nargs=3, metavar=("WAVE", "POLD", "WDIR"), help="parse local GIFs, print JSON, exit")
    ap.add_argument("--time", help="chart time for --files (ISO 8601, default: POLD file mtime)")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    if a.files:
        blobs = [open(p, "rb").read() for p in a.files]
        t = (dt.datetime.fromisoformat(a.time) if a.time
             else dt.datetime.fromtimestamp(os.path.getmtime(a.files[1]), WST))
        if t.tzinfo is None:
            t = t.replace(tzinfo=WST)
        print(json.dumps(build(load_rgb(blobs[0]), load_rgb(blobs[1]), load_rgb(blobs[2]), t.astimezone(WST),
                               station_for_page(a.page)), indent=2))
        return
    if a.once:
        store = Store(None, a.history_days)
        fetch_and_parse(store, station_for_page(a.page))
        print(json.dumps({"status": store.status, "data": store.data}, indent=2))
        return

    slugs = parse_station_list(a.stations)
    if a.out:
        raise SystemExit(update_site(a.out, slugs, a.history_days, max(1, a.attempts), a.attempt_wait))

    minutes = [int(m) for m in a.minutes.split(",") if m.strip()]
    os.makedirs(a.site_dir, exist_ok=True)
    srv = ThreadingHTTPServer((a.host, a.port), make_handler(a.site_dir))
    log.info("serving %s on %s:%d, updating at :%s", a.site_dir, a.host, a.port,
             ", :".join(f"{m:02d}" for m in minutes))
    for base in browse_urls(a.host, a.port):
        log.info("  %s/", base)
        log.info("  %s/stations.json", base)
        log.info("  %s/healthz.json", base)
        log.info("  %s/%s/raw.json", base, DEFAULT_STATION)
    threading.Thread(target=scheduler, args=(a.site_dir, slugs, a.history_days, minutes, a.retry),
                     daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
