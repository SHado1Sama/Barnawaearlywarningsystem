"""
Sensitivity of the v3 design settings: spell cap {4, 6, 8} days x dry gap {1, 2} days.
Uses cumulative.effective_runoff_series' own parameters; same replay scoring as
replay_v3.py. The cap 6 / gap 1 row must reproduce 55 alert days, 35 false, 5 of 6
(revised fixed-CN design on the corrected rainfall series, Addenda 6
and 7 of V3_TEST_REPORT.md).
"""
import sys, os, json
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import forecast, cumulative

HERE = os.path.dirname(os.path.abspath(__file__))
rain = pd.read_csv(os.path.join(HERE, "rain_corrected_1990_2025.csv"), parse_dates=["Date"])
daily = {d.date(): float(v) for d, v in zip(rain["Date"], rain["Precipitation_mm"])}
ews = json.load(open(os.path.join(HERE, "ews_data.json")))
obs = {date.fromisoformat(x["t"]): float(x["q"]) for x in ews["daily_series"]}
WATCH = ews["thresholds"]["watch"]["discharge"]
watch_days = {d for d, q in obs.items() if q >= WATCH}
episodes = [(date.fromisoformat(e["peak_date"]), e["peak_date"][:4]) for e in ews["episodes"]]
DAYS = sorted(daily)
UH = forecast.unit_hydrograph()

def peaks_from_eff(eff_map):
    # identical to replay_v3.py: a forecast issued on day i uses only runoff up to day i
    eff = [eff_map[d] for d in DAYS]; out = {}; N = len(DAYS)
    for i, d in enumerate(DAYS):
        best = 0.0
        for t in range(i, i + forecast.HORIZON_DAYS + 1):
            q = 0.0; jmax = min(t, N - 1, i); jmin = max(0, t - len(UH) + 1)
            for j in range(jmin, jmax + 1):
                k = t - j
                if k < len(UH) and eff[j]: q += eff[j] * UH[k]
            best = max(best, q)
        out[d] = best + forecast.MONTHLY_BASEFLOW[d.month]
    return out

def score(eff):
    peaks = peaks_from_eff(eff)
    alerts = []
    for d in DAYS:
        base = forecast.MONTHLY_BASEFLOW[d.month]
        t = base + forecast.QUICKFLOW_BIAS * (WATCH - base)
        if peaks[d] >= t:
            alerts.append(d)
    aset = set(alerts)
    ver = sum(1 for d in alerts if any(d + timedelta(days=k) in watch_days for k in range(8)))
    caught = [yr for p, yr in episodes if any(p - timedelta(days=7) <= d <= p for d in aset)]
    def clusters(ds):
        n, prev = 0, None
        for d in ds:
            if prev is None or (d - prev).days > 3: n += 1
            prev = d
        return n
    false_days = [d for d in alerts if not any(d + timedelta(days=k) in watch_days for k in range(8))]
    return len(alerts), len(false_days), caught, clusters(alerts), clusters(false_days)

print(f"{'cap':>4} {'gap':>4} {'alerts':>7} {'false':>6} {'caught':>7}  episodes          occasions false_occasions")
for cap in (4, 6, 8):
    for gap in (1, 2):
        eff = cumulative.effective_runoff_series(daily, dry_break_days=gap, max_spell_days=cap)
        a, f, caught, cl, fcl = score(eff)
        print(f"{cap:>4} {gap:>4} {a:>7} {f:>6} {str(len(caught))+'/6':>7}  {','.join(caught):16s} {cl:>9} {fcl:>9}")
