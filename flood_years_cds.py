"""Re-score the six flood years on direct Copernicus CDS rainfall.

Reads rain_cds_flood_years.csv (daily totals built from hourly ERA5
total precipitation downloaded from the Copernicus Climate Data
Store, box average, Africa/Lagos days) and, for contrast, the same
years from rain_era5_redownload_1990_2025.csv. Scoring rules are
identical to replay_v3.py: an alert day is verified when the
observed flow reaches the scored level within the following 7
days; an episode is caught when an alert falls in the 7 days up to
and including its peak. December warm-up days (20 to 31 of the
previous year) come from the archive series in both runs; they
only set soil and spell state on 1 January. Needs ews_data.json
beside it, like the other replay scripts. See Addendum 5 of
V3_TEST_REPORT.md for the results and the data checks.
"""
import json, os, sys
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import amc, forecast, cumulative
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
cds = pd.read_csv(os.path.join(HERE, "rain_cds_flood_years.csv"), parse_dates=["Date"])
cdsmap = {d.date(): float(v) for d, v in zip(cds["Date"], cds["Precipitation_mm"])}
old = pd.read_csv(os.path.join(HERE, "rain_era5_redownload_1990_2025.csv"), parse_dates=["Date"])
oldmap = {d.date(): float(v) for d, v in zip(old["Date"], old["Precipitation_mm"])}
ews = json.load(open(os.path.join(HERE, "ews_data.json")))
thresholds = ews["thresholds"]
observed = {date.fromisoformat(x["t"]): float(x["q"]) for x in ews["daily_series"]}
WATCH = thresholds["watch"]["discharge"]; ADV = ews["advisory_display"]["discharge"]
episodes = {int(e["peak_date"][:4]): date.fromisoformat(e["peak_date"]) for e in ews["episodes"]}
uh = forecast.unit_hydrograph()
cn = dict(zip(("I", "II", "III"), amc.curve_numbers()))

def analyse(daily, year, peak):
    days = sorted(daily); N = len(days)
    def peaks(eff_map):
        eff = [eff_map[d] for d in days]; out = {}
        for i, d in enumerate(days):
            best = 0.0
            for t in range(i, i + forecast.HORIZON_DAYS + 1):
                q = 0.0; jmax = min(t, N - 1, i); jmin = max(0, t - len(uh) + 1)
                for j in range(jmin, jmax + 1):
                    k = t - j
                    if k < len(uh) and eff[j]: q += eff[j] * uh[k]
                best = max(best, q)
            out[d] = best + forecast.MONTHLY_BASEFLOW[d.month]
        return out
    def trig(d, q0):
        b = forecast.MONTHLY_BASEFLOW[d.month]
        return b + forecast.QUICKFLOW_BIAS * (q0 - b)
    def score(pk, level):
        yy = [d for d in days if d.year == year]
        alert = [d for d in yy if pk[d] >= trig(d, level)]
        owatch = {d for d in yy if observed[d] >= level}
        ver = [d for d in alert if any(d + timedelta(days=k) in owatch for k in range(8))]
        w = [d for d in alert if peak - timedelta(days=7) <= d <= peak]
        return {"alerts": len(alert), "false": len(alert) - len(ver),
                "caught": bool(w), "lead": (peak - w[0]).days if w else None}
    def eff_v2(floor):
        out = {}
        for i, d in enumerate(days):
            ante = sum(daily[x] for x in days[max(0, i - 5):i])
            cls = amc.amc_class(ante)
            if floor: cls = amc.apply_wet_season_floor(cls, d)
            out[d] = amc.runoff_mm(daily[d], cn[cls])
        return out
    pk3 = peaks(cumulative.effective_runoff_series(daily, floor=True))
    return {"v2_on": score(peaks(eff_v2(True)), WATCH),
            "v3_watch": score(pk3, WATCH), "v3_adv": score(pk3, ADV)}

for Y in (1999, 2004, 2008, 2012, 2014, 2024):
    warm = {d: v for d, v in oldmap.items() if date(Y - 1, 12, 20) <= d <= date(Y - 1, 12, 31)}
    cds_year = dict(warm); cds_year.update({d: v for d, v in cdsmap.items() if d.year == Y})
    old_year = {d: v for d, v in oldmap.items() if date(Y - 1, 12, 20) <= d <= date(Y, 12, 31)}
    rc = analyse(cds_year, Y, episodes[Y]); ro = analyse(old_year, Y, episodes[Y])
    def f(s): return f"alerts {s['alerts']}, false {s['false']}, caught {s['caught']}, lead {s['lead']}"
    print(f"{Y} CDS:  v2 {f(rc['v2_on'])} | v3 Watch {f(rc['v3_watch'])} | v3 Advisory caught {rc['v3_adv']['caught']}")
    print(f"{Y} arch: v2 {f(ro['v2_on'])} | v3 Watch {f(ro['v3_watch'])} | v3 Advisory caught {ro['v3_adv']['caught']}")
