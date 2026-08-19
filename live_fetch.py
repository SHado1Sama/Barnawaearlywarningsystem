"""
Barnawa EWS - live conditions fetch.

Pulls real, currently-available data (no API key required) and writes
EWS_System/live_data.json:

  1. Rainfall (Open-Meteo Forecast API) at the catchment centroid
     (10.634 N, 7.753 E) - past 2 days observed + 7 days forecast, hourly.
     This is the primary live signal: it feeds the same 24h/20mm trigger
     logic used for the 2012/2022 historical case studies.

  2. Discharge (GEOGloWS v2 API) for the mapped global forecast reach at
     the catchment's documented outlet (10.4700 N, 7.4500 E, Table 3.1) -
     river_id 140653280, ~5.5 km away (looked up once via
     /api/v2/getriverid). Verified identical to this study's own daily
     streamflow record: the reach's 1990-2025 retrospective series and
     barnawa_Daily_Streamflow_1990_2025.csv overlap for 13,149 days with
     zero discrepancy (max abs diff 0.0000 m3/s), confirming this is the
     same reach/segment the study's record is derived from (Section 4.7),
     not merely a nearby proxy. The median forecast is therefore
     classified directly against the GEV thresholds in ews_data.json
     (the 25th-75th percentile band is still shown, but only the median
     is classified, to avoid over-warning on the upper band).

Run on a schedule (see setup_scheduled_task.ps1) or manually. Safe to
run with no internet: writes a status:"error" record instead of crashing,
so the dashboard can show "live data unavailable" rather than go stale
silently or throw.
"""
import json
import math
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

LAT, LON = 10.4700, 7.4500
GEOGLOWS_RIVER_ID = 140653280
GEOGLOWS_DIST_KM = 5.5
RAIN_TRIGGER_MM_24H = 20.0
OUT_PATH = "live_data.json"
EWS_DATA_PATH = "ews_data.json"
HISTORY_PATH = "history.json"
MAX_HISTORY_RECORDS = 1825  # ~5 years at one snapshot/day
TIMEOUT = 20
LEVEL_ORDER = ["normal", "watch", "warning", "emergency"]


def load_thresholds():
    with open(EWS_DATA_PATH) as f:
        return json.load(f)["thresholds"]


def classify_discharge(q, thresholds):
    if q >= thresholds["emergency"]["discharge"]:
        return "emergency"
    if q >= thresholds["warning"]["discharge"]:
        return "warning"
    if q >= thresholds["watch"]["discharge"]:
        return "watch"
    return "normal"


RETRY_DELAYS_S = (3, 8, 15)  # GEOGloWS occasionally 400s on the CI runner's IP for no
                              # reproducible reason (works fine locally); a short retry
                              # clears most of these rather than dropping the whole
                              # discharge forecast for a full 30-minute cycle.


def fetch_json(url):
    last_err = None
    for attempt, delay in enumerate((0,) + RETRY_DELAYS_S):
        if delay:
            time.sleep(delay)
        req = urllib.request.Request(url, headers={"User-Agent": "barnawa-ews/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode())
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            last_err = e
    raise last_err


def fetch_rainfall():
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}"
        "&hourly=precipitation&past_days=2&forecast_days=7&timezone=UTC"
    )
    d = fetch_json(url)
    times = d["hourly"]["time"]
    precip = d["hourly"]["precipitation"]
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    now_str = now.strftime("%Y-%m-%dT%H:%M")

    series = [{"t": t, "mm": (p if p is not None else 0.0)} for t, p in zip(times, precip)]
    observed = [pt for pt in series if pt["t"] <= now_str]
    forecast = [pt for pt in series if pt["t"] > now_str]

    def rolling24(points, end_idx):
        start = max(0, end_idx - 23)
        return sum(p["mm"] for p in points[start:end_idx + 1])

    # trigger search across the whole observed+forecast series (past 48h real,
    # next 7 days forecast) so both "already triggered" and "about to trigger"
    # are detected
    trigger_time = None
    trigger_is_forecast = False
    for i in range(len(series)):
        r24 = rolling24(series, i)
        if r24 >= RAIN_TRIGGER_MM_24H:
            trigger_time = series[i]["t"]
            trigger_is_forecast = series[i]["t"] > now_str
            break

    obs_r24 = rolling24(observed, len(observed) - 1) if observed else 0.0

    return {
        "source": "Open-Meteo Forecast API",
        "lat": LAT, "lon": LON,
        "as_of": now_str,
        "rolling_24h_mm": round(obs_r24, 1),
        "trigger_threshold_mm_24h": RAIN_TRIGGER_MM_24H,
        "trigger_time": trigger_time,
        "trigger_is_forecast": trigger_is_forecast,
        "observed": observed[-72:],
        "forecast": forecast[:168],
    }


def fetch_geoglows():
    thresholds = load_thresholds()
    fstats = fetch_json(f"https://geoglows.ecmwf.int/api/v2/forecaststats/{GEOGLOWS_RIVER_ID}?format=json")
    retro = fetch_json(f"https://geoglows.ecmwf.int/api/v2/retrospectivedaily/{GEOGLOWS_RIVER_ID}?format=json")
    retro_vals = sorted(v for v in retro[str(GEOGLOWS_RIVER_ID)] if isinstance(v, (int, float)))

    def percentile_of(value):
        if not retro_vals or value is None:
            return None
        import bisect
        pos = bisect.bisect_left(retro_vals, value)
        return round(100 * pos / len(retro_vals), 1)

    dt = fstats["datetime"]
    rows = []
    for i, t in enumerate(dt):
        med = fstats["flow_med"][i]
        if med == "" or med is None:
            continue
        rows.append({
            "t": t,
            "med": med,
            "p25": fstats["flow_25p"][i] if fstats["flow_25p"][i] != "" else med,
            "p75": fstats["flow_75p"][i] if fstats["flow_75p"][i] != "" else med,
            "pct": percentile_of(med),
            "lvl": classify_discharge(med, thresholds),
        })

    current_level = rows[0]["lvl"] if rows else None
    max_level = max((r["lvl"] for r in rows), key=lambda lvl: LEVEL_ORDER.index(lvl)) if rows else None

    return {
        "source": "GEOGloWS v2 forecast (verified same reach as Barnawa's streamflow record)",
        "river_id": GEOGLOWS_RIVER_ID,
        "distance_km": GEOGLOWS_DIST_KM,
        "retrospective_years": round(len(retro_vals) / 365.25, 1),
        "retrospective_mean": round(sum(retro_vals) / len(retro_vals), 2) if retro_vals else None,
        "current_level": current_level,
        "max_level": max_level,
        "forecast": rows,
    }


def append_history(out):
    """Append one snapshot per UTC calendar day to history.json, so the dashboard
    can show recent days without a git commit on every 30-minute fetch: once
    today's date is already recorded, later fetches the same day are a no-op
    (first successful fetch of the day wins). Skipped entirely when both
    sources failed, so a fully-dead fetch doesn't pollute the record with an
    all-null row."""
    r, g = out.get("rainfall"), out.get("geoglows")
    if not r and not g:
        return
    day = out["fetched_at"][:10]
    try:
        with open(HISTORY_PATH) as f:
            hist = json.load(f)
        if not isinstance(hist, list):
            hist = []
    except (FileNotFoundError, json.JSONDecodeError):
        hist = []
    if hist and hist[-1].get("date") == day:
        return
    hist.append({
        "date": day,
        "t": out["fetched_at"],
        "rain24": r["rolling_24h_mm"] if r else None,
        "flow": g["forecast"][0]["med"] if g and g["forecast"] else None,
        "level": g["current_level"] if g else None,
    })
    if len(hist) > MAX_HISTORY_RECORDS:
        hist = hist[-MAX_HISTORY_RECORDS:]
    with open(HISTORY_PATH, "w") as f:
        json.dump(hist, f)


def main():
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = {"fetched_at": fetched_at, "status": "ok", "error": None}
    try:
        out["rainfall"] = fetch_rainfall()
    except Exception as e:
        out["status"] = "error"
        out["error"] = f"rainfall fetch failed: {e}"
        out["rainfall"] = None
    try:
        out["geoglows"] = fetch_geoglows()
    except Exception as e:
        if out["status"] == "ok":
            out["status"] = "partial"
        out["error"] = (out["error"] + " | " if out["error"] else "") + f"geoglows fetch failed: {e}"
        out["geoglows"] = None

    with open(OUT_PATH, "w") as f:
        json.dump(out, f)
    append_history(out)
    print(fetched_at, out["status"], out["error"] or "")


if __name__ == "__main__":
    main()
