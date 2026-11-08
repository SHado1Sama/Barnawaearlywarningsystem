"""
Barnawa EWS - rainfall-driven forecast replay (stdlib only).

This is the forecast mode of the offline simulation (barnawa_ews.py) rewritten
without numpy, so the GitHub Actions runner needs nothing extra. It is used to
replay the two stored flood seasons (2012, 2022) and show, on the dashboard,
what the forecast would have said with and without the wet-season floor on soil
wetness (amc.py).

Each day the model is run FORWARD using only the rain that had fallen up to that
day, assuming no further rain:

  1. 5-day antecedent rainfall picks the soil class (AMC I / II / III) and so the
     curve number (amc.py). With the wet-season floor, July to September never
     uses AMC I.
  2. SCS curve number turns the day's rain into effective rain (runoff, mm).
  3. A daily SCS unit hydrograph (catchment 3,808.9 km2, lag 62.9 h) turns the
     effective rain into discharge.
  4. The predicted peak over the next 7 days plus the monthly baseflow is compared
     with the FORECAST triggers. The model under-predicts flood peaks, so the
     observed design discharges (Watch 1,836 m3/s etc.) cannot be used directly.
     The triggers are scaled by the under-prediction measured at the 2004
     calibration event, but only on the QUICKFLOW part (the flow above the monthly
     baseflow), because the baseflow is added to the forecast at its true value
     and is not under-predicted:

         trigger(level, month) = baseflow(month) + k * (design_Q(level) - baseflow(month))
         k = (711.4 - 199.6) / (3496.9 - 199.6) = 0.155      (2004 event, August)

     The earlier version scaled the whole design discharge (x 0.2038, so Watch =
     374 m3/s). In September the baseflow alone is 341 m3/s, 91% of that trigger,
     so ordinary rain pushed the forecast over it and 2022 produced 13 false-alarm
     days. Set BASEFLOW_AWARE_TRIGGERS = False to go back to the earlier triggers.

Limits: rainfall is one grid cell near the catchment, not a catchment average, so
the figures are indicative. The check covers two of the 36 seasons only.
"""
import math
from datetime import date, timedelta

import amc

CATCHMENT_AREA_KM2 = 3808.9286
LAG_HOURS = 3776.2 / 60.0
FORECAST_BIAS = 0.2038          # earlier method: whole design discharge x 0.2038 (peak ratio, 2004 event)
BASEFLOW_AWARE_TRIGGERS = True  # False = earlier triggers (Watch 374 m3/s in every month)
PEAK_2004_FORECAST = 711.372    # forecast peak, 2004 event (lead_time_analysis.csv)
PEAK_2004_OBSERVED = 3496.94    # observed peak, 24 Aug 2004
HORIZON_DAYS = 7
LEVELS = ["normal", "watch", "warning", "emergency"]

# Monthly baseflow, m3/s (Lyne-Hollick filter, 1990-2025)
MONTHLY_BASEFLOW = {
    1: 26.0, 2: 16.6, 3: 10.9, 4: 8.0, 5: 10.2, 6: 24.3,
    7: 67.1, 8: 199.6, 9: 341.2, 10: 198.8, 11: 84.8, 12: 44.5,
}


def unit_hydrograph(dt_hours=24.0):
    """Daily SCS triangular unit hydrograph, normalised to 1 mm over the catchment."""
    tp = dt_hours / 2.0 + LAG_HOURS
    tb = 2.67 * tp
    qp = 0.208 * CATCHMENT_AREA_KM2 / tp
    n = int(math.ceil(tb / dt_hours)) + 1
    u = []
    for k in range(n):
        t = k * dt_hours
        u.append(qp * t / tp if t <= tp else qp * max(0.0, (tb - t) / (tb - tp)))
    target = CATCHMENT_AREA_KM2 * 1e6 * 1e-3          # m3 per mm
    actual = sum(u) * dt_hours * 3600.0
    return [x * target / actual for x in u]


QUICKFLOW_BIAS = (PEAK_2004_FORECAST - MONTHLY_BASEFLOW[8]) / (PEAK_2004_OBSERVED - MONTHLY_BASEFLOW[8])


def forecast_triggers(thresholds, month, baseflow_aware=None):
    """
    Forecast trigger levels (m3/s, total flow including baseflow) for a calendar month,
    from the design-discharge thresholds in ews_data.json.
    """
    if baseflow_aware is None:
        baseflow_aware = BASEFLOW_AWARE_TRIGGERS
    base = MONTHLY_BASEFLOW[month]
    out = {}
    for k in ("watch", "warning", "emergency"):
        q = thresholds[k]["discharge"]
        out[k] = base + QUICKFLOW_BIAS * (q - base) if baseflow_aware else q * FORECAST_BIAS
    return out


def classify(q, triggers):
    if q >= triggers["emergency"]:
        return "emergency"
    if q >= triggers["warning"]:
        return "warning"
    if q >= triggers["watch"]:
        return "watch"
    return "normal"


def predicted_peaks(daily_mm, floor, horizon=HORIZON_DAYS):
    """
    daily_mm: {date: rain mm}, consecutive days. Returns {date: predicted peak m3/s}
    using only rain up to and including that date.
    """
    peaks, _ = predicted_peaks_and_lag(daily_mm, floor, horizon)
    return peaks


def predicted_peaks_and_lag(daily_mm, floor, horizon=HORIZON_DAYS):
    """As predicted_peaks, also returning {date: days until the predicted peak}."""
    days = sorted(daily_mm)
    rain = [daily_mm[d] for d in days]
    cn_by_class = dict(zip(("I", "II", "III"), amc.curve_numbers()))
    uh = unit_hydrograph()

    effective = []
    for i, d in enumerate(days):
        antecedent = sum(rain[max(0, i - amc.ANTECEDENT_DAYS):i])
        cls = amc.amc_class(antecedent)
        if floor:
            cls = amc.apply_wet_season_floor(cls, d)
        effective.append(amc.runoff_mm(rain[i], cn_by_class[cls]))

    out, lag = {}, {}
    for i, d in enumerate(days):
        q = [0.0] * (i + horizon + 1)
        for j in range(i + 1):
            if effective[j] == 0.0:
                continue
            for k, uk in enumerate(uh):
                if j + k < len(q):
                    q[j + k] += effective[j] * uk
        window = q[i:i + horizon + 1]
        out[d] = max(window) + MONTHLY_BASEFLOW[d.month]
        lag[d] = window.index(max(window))
    return out, lag


def _outcome(forecast_level, observed_level):
    f, o = LEVELS.index(forecast_level), LEVELS.index(observed_level)
    if f == 0 and o > 0:
        return "missed"
    if f > 0 and o == 0:
        return "false_alarm"
    if f > 0 and o > 0:
        return "caught"
    return "quiet"


def replay_case(cs, thresholds):
    """
    Replay one stored case study (ews_data.json case_studies entry) with and without
    the wet-season floor. Returns a JSON-ready dict for the dashboard.
    """
    daily = amc.daily_totals(cs["rainfall_hourly"])
    raw = predicted_peaks(daily, floor=False)
    flo = predicted_peaks(daily, floor=True)
    days = sorted(daily)

    # Decision day: the heaviest-rain day in the 7 days up to the observed peak.
    peak_day = date.fromisoformat(cs["peak_time"][:10])
    window = [d for d in days if peak_day - timedelta(days=HORIZON_DAYS) <= d <= peak_day]
    dd = max(window, key=lambda d: daily[d])

    before = sum(daily.get(dd - timedelta(days=k), 0.0) for k in range(1, amc.ANTECEDENT_DAYS + 1))
    raw_cls = amc.amc_class(before)
    flo_cls = amc.apply_wet_season_floor(raw_cls, dd)
    cn = dict(zip(("I", "II", "III"), amc.curve_numbers()))

    trig_by_day = {d: forecast_triggers(thresholds, d.month) for d in days}
    triggers = trig_by_day[dd]
    lvl_raw = classify(raw[dd], triggers)
    lvl_flo = classify(flo[dd], triggers)
    alert_raw = [d for d in days if raw[d] >= trig_by_day[d]["watch"]]
    alert_flo = [d for d in days if flo[d] >= trig_by_day[d]["watch"]]
    added = [d for d in alert_flo if d not in alert_raw]

    return {
        "baseflow_aware": BASEFLOW_AWARE_TRIGGERS,
        "quickflow_bias": round(QUICKFLOW_BIAS, 4),
        "baseflow_m3s": MONTHLY_BASEFLOW[dd.month],
        "triggers": {k: round(v, 1) for k, v in triggers.items()},
        "wet_season_months": list(amc.WET_SEASON_MONTHS),
        "days": [{"t": d.isoformat(), "raw": round(raw[d], 1), "floor": round(flo[d], 1),
                  "trig": round(trig_by_day[d]["watch"], 1)} for d in days],
        "decision": {
            "date": dd.isoformat(),
            "rain_mm": round(daily[dd], 1),
            "antecedent_5d_mm": round(before, 1),
            "class_raw": raw_cls,
            "class_floor": flo_cls,
            "ia_raw_mm": round(amc.initial_abstraction(cn[raw_cls]), 1),
            "ia_floor_mm": round(amc.initial_abstraction(cn[flo_cls]), 1),
            "peak_raw": round(raw[dd], 1),
            "peak_floor": round(flo[dd], 1),
            "level_raw": lvl_raw,
            "level_floor": lvl_flo,
            "outcome_raw": _outcome(lvl_raw, cs["peak_level"]),
            "outcome_floor": _outcome(lvl_flo, cs["peak_level"]),
            "days_before_peak": (peak_day - dd).days,
        },
        "alert_days_raw": len(alert_raw),
        "alert_days_floor": len(alert_flo),
        "added_days": {
            "count": len(added),
            "first": added[0].isoformat() if added else None,
            "last": added[-1].isoformat() if added else None,
        },
    }


def live_model(full_series, now_str, thresholds, recent_days=7):
    """
    Run the forecast on the live rainfall: Open-Meteo hourly rain up to now (a few weeks of
    history, so soil wetness and the tail of earlier storms are known), assuming no further
    rain, exactly as in the validated replay. The rain still to come is ignored on purpose:
    forecast rain has not been tested against the historical record.

    full_series: hourly points [{'t': 'YYYY-MM-DDTHH:MM', 'mm': x}, ...] (past + forecast)
    now_str:     current UTC hour 'YYYY-MM-DDTHH:MM'; later points are not used
    Returns the dict stored under live_data.json -> rainfall.model.
    """
    observed = [p for p in full_series if p["t"] <= now_str]
    daily = amc.daily_totals(observed)
    today = date.fromisoformat(now_str[:10])
    raw, _ = predicted_peaks_and_lag(daily, floor=False)
    flo, lag = predicted_peaks_and_lag(daily, floor=True)
    days = sorted(daily)

    cn_name = {"I": "dry", "II": "average", "III": "wet"}

    def soil(d):
        total, _found = amc.antecedent_total(daily, d)
        cls = amc.amc_class(total)
        return cls, amc.apply_wet_season_floor(cls, d), total

    trig_today = forecast_triggers(thresholds, today.month)
    cls_raw, cls_used, ante = soil(today)
    recent = []
    for d in days[-recent_days:]:
        t = forecast_triggers(thresholds, d.month)
        c_raw, c_used, _ = soil(d)
        recent.append({
            "t": d.isoformat(), "rain_mm": round(daily[d], 1), "soil": c_used, "soil_raw": c_raw,
            "peak": round(flo[d], 1), "level": classify(flo[d], t),
        })
    return {
        "method": "SCS curve number with antecedent moisture and a July-September floor, daily unit hydrograph, monthly baseflow",
        "as_of": now_str,
        "today": today.isoformat(),
        "history_days": len(days),
        "floor_active": today.month in amc.WET_SEASON_MONTHS,
        "baseflow_aware": BASEFLOW_AWARE_TRIGGERS,
        "baseflow_m3s": MONTHLY_BASEFLOW[today.month],
        "rain_today_mm": round(daily[today], 1),
        "soil": cls_used, "soil_raw": cls_raw, "soil_name": cn_name[cls_used],
        "antecedent_5d_mm": round(ante, 1),
        "predicted_peak": round(flo[today], 1),
        "days_to_peak": lag[today],
        "level": classify(flo[today], trig_today),
        "predicted_peak_without_floor": round(raw[today], 1),
        "level_without_floor": classify(raw[today], trig_today),
        "triggers": {k: round(v, 1) for k, v in trig_today.items()},
        "recent": recent,
    }
