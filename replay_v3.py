"""Full 36-year replay of the v3 bounded cumulative model, scored exactly as replay_36yr.py scored v2.

Scores the revised design of 9 Nov 2026 (curve number fixed at CN II, no AMC
classes, no wet-season floor; see Addendum 6 of V3_TEST_REPORT.md) on the
corrected rainfall series (rain_corrected_1990_2025.csv: the archive
re-download with 2024 and 2025 replaced by the direct Copernicus CDS
series; Addenda 7 and 8). The original design's replay figures are
preserved in the report.
"""
import json, os, sys
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import amc, forecast, cumulative
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
rain = pd.read_csv(os.path.join(HERE, "rain_corrected_1990_2025.csv"), parse_dates=["Date"])
daily_mm = {d.date(): float(v) for d, v in zip(rain["Date"], rain["Precipitation_mm"])}
ews = json.load(open(os.path.join(HERE, "ews_data.json")))
thresholds = ews["thresholds"]
observed = {date.fromisoformat(x["t"]): float(x["q"]) for x in ews["daily_series"]}
episodes = ews["episodes"]; WATCH = thresholds["watch"]["discharge"]
days = sorted(daily_mm); uh = forecast.unit_hydrograph(); N = len(days)

def peaks_from_eff(eff_map):
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

def score(peaks):
    trig = {d: forecast.forecast_triggers(thresholds, d.month) for d in days}
    alert = [d for d in days if peaks[d] >= trig[d]["watch"]]
    obs_watch = {d for d in days if observed[d] >= WATCH}
    ver = [d for d in alert if any(d + timedelta(days=k) in obs_watch for k in range(8))]
    ev = []
    for e in episodes:
        p = date.fromisoformat(e["peak_date"])
        w = [d for d in alert if p - timedelta(days=7) <= d <= p]
        ev.append({"peak_date": e["peak_date"], "peak_level": e["peak_level"], "peak_discharge": e["peak_discharge"],
                   "caught": bool(w), "lead_days": (p - w[0]).days if w else None})
    return {"alert_days": len(alert), "verified": len(ver), "false_alarm_days": len(alert) - len(ver),
            "episodes_caught": sum(1 for x in ev if x["caught"]), "episodes": ev,
            "alert_dates": [d.isoformat() for d in alert]}

eff = cumulative.effective_runoff_series(daily_mm)
peaks = peaks_from_eff(eff)
s = score(peaks)
print(f"v3 fixed CN II: alerts {s['alert_days']}, verified {s['verified']}, false {s['false_alarm_days']}, caught {s['episodes_caught']}/6")
print("   episodes:", [(e["peak_date"], e["caught"], e["lead_days"]) for e in s["episodes"]])

rows = [{"Date": d.isoformat(), "Rain_mm": round(daily_mm[d], 3), "Observed_Q_m3s": observed[d],
         "PredPeak_V3_m3s": round(peaks[d], 1),
         "Forecast_Watch_Trigger_m3s": round(forecast.forecast_triggers(thresholds, d.month)["watch"], 1)} for d in days]
pd.DataFrame(rows).to_csv(os.path.join(HERE, "daily_replay_v3.csv"), index=False)
json.dump({"fixed_cn2": s}, open(os.path.join(HERE, "replay_v3_summary.json"), "w"), indent=2)

# Case-study seasons under v3 (rainfall as stored in ews_data.json, as replay_case uses)
for cs in ews["case_studies"]:
    daily = amc.daily_totals(cs["rainfall_hourly"])
    ds = sorted(daily)
    eff_map = cumulative.effective_runoff_series(daily)
    eff = [eff_map[d] for d in ds]; pk = {}
    for i, d in enumerate(ds):
        best = 0.0
        for t in range(i, i + 8):
            q = 0.0; jmax = min(t, len(ds) - 1, i); jmin = max(0, t - len(uh) + 1)
            for j in range(jmin, jmax + 1):
                k = t - j
                if k < len(uh) and eff[j]: q += eff[j] * uh[k]
            best = max(best, q)
        pk[d] = best + forecast.MONTHLY_BASEFLOW[d.month]
    trig = {d: forecast.forecast_triggers(thresholds, d.month) for d in ds}
    alerts = [d for d in ds if pk[d] >= trig[d]["watch"]]
    print(f"case {cs['year']}: season alert days {len(alerts)}", [d.isoformat() for d in alerts][:10])
