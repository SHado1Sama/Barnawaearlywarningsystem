"""
Checks for amc.py. Run from the repository folder:  python test_amc.py
Prints PASS and exits 0 when everything matches the report; stops with an error otherwise.
"""
import json
from datetime import date

import amc
import forecast


def close(a, b, tol):
    return abs(a - b) <= tol


# 1. Curve numbers and initial abstractions quoted in the report (Sections 3.7.2, 4.6.2, Appendix)
cn1, cn2, cn3 = amc.curve_numbers()
assert close(cn1, 48.69, 0.01), cn1
assert close(cn2, 69.321, 0.001), cn2
assert close(cn3, 83.86, 0.01), cn3
assert close(amc.initial_abstraction(cn1), 53.5, 0.1)
assert close(amc.initial_abstraction(cn2), 22.5, 0.1)
assert close(amc.initial_abstraction(cn3), 9.8, 0.1)

# 2. Class boundaries: below 35 dry, 35 to 53 average, above 53 wet
assert amc.amc_class(0) == "I"
assert amc.amc_class(34.99) == "I"
assert amc.amc_class(35.0) == "II"
assert amc.amc_class(53.0) == "II"
assert amc.amc_class(53.01) == "III"

# 3. Runoff: nothing below Ia, and the same rain gives more runoff on wetter soil
assert amc.runoff_mm(9.0, cn3) == 0.0
assert amc.runoff_mm(20.0, cn1) == 0.0
r1, r2, r3 = (amc.runoff_mm(60.0, c) for c in (cn1, cn2, cn3))
assert 0 < r1 < r2 < r3, (r1, r2, r3)

# 4. Antecedent window is the 5 days BEFORE the day, current day excluded
daily = {date(2026, 8, d): 10.0 for d in range(1, 11)}
daily[date(2026, 8, 10)] = 99.0          # the day itself must not count
total, found = amc.antecedent_total(daily, date(2026, 8, 10))
assert total == 50.0 and found == 5, (total, found)

# 5. Real stored events: 2012 and 2022 hourly rain from ews_data.json
data = json.load(open("ews_data.json"))
for cs in data["case_studies"]:
    d = amc.daily_totals(cs["rainfall_hourly"])
    trig = cs["trigger_time"]
    if trig:
        blk = amc.build_live_amc(cs["rainfall_hourly"], date.fromisoformat(trig[:10]), trigger_time=trig,
                                 trigger_rain_24h_mm=20.0)
        t = blk["trigger"]
        print(cs["year"], "storm began", t["storm_start"], "->", t["antecedent_5d_mm"], "mm in the 5 days before:",
              "AMC", t["amc"], t["condition"], "CN", t["cn"])
        if cs["year"] == 2012:
            # 31 mm in the 5 days before the storm: the 5-day rule alone says dry (the cause of the miss),
            # and the wet-season floor lifts it to average because the storm began in August
            assert t["amc_raw"] == "I" and t["amc"] == "II" and t["floor_applied"], t

# 6. build_live_amc returns the structure the dashboard reads
series = [{"t": f"2026-08-{d:02d}T{h:02d}:00", "mm": 0.5} for d in range(1, 15) for h in range(24)]
blk = amc.build_live_amc(series, date(2026, 8, 8), trigger_time="2026-08-10T12:00",
                         trigger_rain_24h_mm=25.0, rain_24h_mm=12.0)
assert blk["now"]["antecedent_5d_mm"] == 60.0 and blk["now"]["amc"] == "III"
assert blk["trigger"]["amc"] == "III" and blk["trigger"]["runoff_24h_mm"] > 0
assert amc.build_live_amc(series, date(2026, 8, 8))["trigger"] is None

# 7. Wet-season floor: dry becomes average in July, August, September only; wet and average are untouched
dry = {date(2026, m, d): 1.0 for m in (6, 7, 8, 9, 10, 11) for d in range(1, 29)}   # 5 mm in any 5 days: dry
for month, expected in ((6, "I"), (7, "II"), (8, "II"), (9, "II"), (10, "I"), (11, "I")):
    r = amc.describe(dry, date(2026, month, 20))
    assert r["amc_raw"] == "I" and r["amc"] == expected, (month, r)
assert amc.describe(dry, date(2026, 8, 20), wet_season_floor=False)["amc"] == "I"
assert amc.apply_wet_season_floor("III", date(2026, 8, 1)) == "III"
assert amc.apply_wet_season_floor("II", date(2026, 8, 1)) == "II"

# 8. Forecast replay of the 2012 miss: the model matches the report and the floor corrects it
data = json.load(open("ews_data.json"))
cs12 = [c for c in data["case_studies"] if c["year"] == 2012][0]
cs22 = [c for c in data["case_studies"] if c["year"] == 2022][0]
thr = data["thresholds"]

# 8a. Triggers: baseflow plus k x (design flow - baseflow), k from the 2004 event; Watch rises through the season
k = forecast.QUICKFLOW_BIAS
assert close(k, (711.372 - 199.6) / (3496.94 - 199.6), 1e-4) and close(k, 0.1552, 0.0005), k
assert close(forecast.forecast_triggers(thr, 7)["watch"], 341.6, 0.2)
assert close(forecast.forecast_triggers(thr, 8)["watch"], 453.6, 0.2)
assert close(forecast.forecast_triggers(thr, 9)["watch"], 573.2, 0.2)
assert close(forecast.forecast_triggers(thr, 9, baseflow_aware=False)["watch"], 374.2, 0.1)   # earlier method

m12 = forecast.replay_case(cs12, thr)
d12 = m12["decision"]
trig = m12["triggers"]["watch"]
assert close(trig, 453.6, 0.2), trig
assert d12["date"] == "2012-08-24" and close(d12["antecedent_5d_mm"], 31.1, 0.1), d12
assert d12["class_raw"] == "I" and d12["class_floor"] == "II", d12
assert close(d12["peak_raw"], 263, 2) and close(d12["peak_floor"], 505, 2), d12   # figures in the report
assert d12["peak_raw"] < trig <= d12["peak_floor"], d12
assert d12["outcome_raw"] == "missed" and d12["outcome_floor"] == "caught", d12
assert d12["days_before_peak"] >= 1, d12
# no alert days without the floor; with it, only the days of the real flood
assert m12["alert_days_raw"] == 0 and m12["alert_days_floor"] == m12["added_days"]["count"] == 5, m12
assert m12["added_days"]["first"] == "2012-08-24" and m12["added_days"]["last"] == "2012-08-28", m12

# 2022: no false alarm with the baseflow-aware triggers, with or without the floor
m22 = forecast.replay_case(cs22, thr)
assert m22["alert_days_raw"] == m22["alert_days_floor"] == 0, m22
assert m22["decision"]["outcome_raw"] == m22["decision"]["outcome_floor"] == "quiet", m22["decision"]
assert m22["decision"]["class_raw"] == m22["decision"]["class_floor"] == "III", m22["decision"]

# 8b. The earlier triggers (Watch 374 m3/s every month) are what produced the 2022 false alarms: 13 days
daily22 = amc.daily_totals(cs22["rainfall_hourly"])
peaks22 = forecast.predicted_peaks(daily22, floor=True)
old = [d for d in peaks22 if peaks22[d] >= forecast.forecast_triggers(thr, d.month, baseflow_aware=False)["watch"]]
assert len(old) == 13, len(old)
print("2012 forecast peak", d12["peak_raw"], "->", d12["peak_floor"], "m3/s vs Aug Watch trigger", trig,
      "|", d12["outcome_raw"], "->", d12["outcome_floor"], "| alert days", m12["alert_days_raw"], "->", m12["alert_days_floor"],
      "| 2022 alert days", len(old), "(earlier triggers) ->", m22["alert_days_floor"], "(baseflow-aware)")

# 9. Live block: a dry November has no floor, a dry August does
nov = [{"t": f"2026-11-{d:02d}T{h:02d}:00", "mm": 0.0} for d in range(1, 15) for h in range(24)]
aug = [{"t": f"2026-08-{d:02d}T{h:02d}:00", "mm": 0.0} for d in range(1, 15) for h in range(24)]
bn = amc.build_live_amc(nov, date(2026, 11, 8))["now"]
ba = amc.build_live_amc(aug, date(2026, 8, 8))["now"]
assert bn["amc"] == "I" and not bn["floor_applied"], bn
assert ba["amc"] == "II" and ba["amc_raw"] == "I" and ba["floor_applied"], ba

# 10. Live model: a heavy August storm after a dry spell gives Watch with the floor and Normal without it;
#     a dry November gives Normal with the floor off
def hourly(days, month, storm_day=None):
    pts = []
    for d in days:
        for h in range(24):
            mm = 0.05
            if storm_day == d and 6 <= h <= 17:
                mm = 8.0
            pts.append({"t": f"2026-{month:02d}-{d:02d}T{h:02d}:00", "mm": mm})
    return pts

wet = forecast.live_model(hourly(range(1, 25), 8, storm_day=24), "2026-08-24T20:00", thr)
assert wet["floor_active"] and wet["soil"] == "II" and wet["soil_raw"] == "I", wet
assert wet["level"] == "watch" and wet["level_without_floor"] == "normal", wet
assert wet["predicted_peak"] > wet["triggers"]["watch"] > wet["predicted_peak_without_floor"], wet
assert wet["days_to_peak"] >= 1 and len(wet["recent"]) == 7, wet
dry = forecast.live_model(hourly(range(1, 9), 11), "2026-11-08T02:00", thr)
assert not dry["floor_active"] and dry["level"] == "normal" and dry["soil"] == "I", dry
assert close(dry["predicted_peak"], forecast.MONTHLY_BASEFLOW[11], 0.5), dry   # only baseflow when it is dry
# rain after "now" is ignored
later = hourly(range(1, 25), 8, storm_day=24)
assert forecast.live_model(later, "2026-08-24T05:00", thr)["level"] == "normal"

print("PASS")
