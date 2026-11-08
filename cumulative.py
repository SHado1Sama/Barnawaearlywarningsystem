"""
Barnawa EWS - bounded cumulative abstraction (v3, EXPERIMENTAL, supplementary advisory only).

Why: in v2 (forecast.py), every day's rain is fed to the SCS runoff equation
as if that day were a whole storm, so the initial abstraction Ia = lambda * S
(lambda = 0.20) is charged in full every day. Rain below Ia produces zero
runoff and is forgotten, which is why the spread-out July 2024 rains
(160 mm in the month, wettest day 15.1 mm, Ia 22.5 mm) generated no runoff
at all in v2 while the river rose to 2,017 m3/s.

What changes here, and only here: Ia is charged ONCE per wet spell against
the spell's CUMULATIVE rainfall, and each day's runoff is the increment of
cumulative runoff, exactly the procedure NRCS NEH Part 630 Subpart H uses
to spread runoff through a storm ("tabulate the accumulated rainfalls,
estimate the accumulated runoff, compute the increments of runoff"):
    Pc(t) = rain accumulated since the spell began
    Qc(t) = (Pc - Ia)^2 / (Pc - Ia + S)  for Pc > Ia, else 0
    runoff(t) = Qc(t) - Qc(t-1)

The bound (what makes this v3 rather than the rejected raw version):
  - A spell is at most MAX_SPELL_DAYS = 6 days: the storm day plus the same
    5 antecedent days the AMC logic already uses as the soil's memory.
    After 6 days a new spell starts and Ia is charged again.
  - A spell also ends after DRY_BREAK_DAYS = 1 day with rain below
    WET_DAY_MM = 1.0 mm.
  - CN (and so S and Ia) is fixed at the spell start, from the AMC class of
    the 5 days before the spell, with the wet-season floor applied exactly
    as in v2 when floor=True.
  - lambda stays 0.20, the value the published CN set was built with.

Everything downstream is v2 unchanged: unit hydrograph, monthly baseflow,
baseflow-aware triggers, classification.

Honest status, from the full 36-year test (V3_TEST_REPORT.md): this catches
4 of 6 observed flood episodes (v2: 2 of 6) but at 68 alert days with 52
false alarm days (v2: 12 and 2). It still does NOT catch 2024. It is a
detection-first experimental variant, not a replacement for v2.
"""
import amc

LAMBDA = 0.20
WET_DAY_MM = 1.0
DRY_BREAK_DAYS = 1
MAX_SPELL_DAYS = 6


def cumulative_runoff(Pc, S, lam=LAMBDA):
    """SCS cumulative runoff depth (mm) for cumulative rain Pc (mm)."""
    Ia = lam * S
    if Pc <= Ia:
        return 0.0
    return (Pc - Ia) ** 2 / (Pc - Ia + S)


def effective_runoff_series(daily_mm, floor=True, lam=LAMBDA,
                            dry_break_days=DRY_BREAK_DAYS,
                            max_spell_days=MAX_SPELL_DAYS,
                            wet_day_mm=WET_DAY_MM):
    """
    daily_mm: {date: rain mm} (any subset; processed in date order).
    Returns {date: runoff mm for that day} under bounded cumulative abstraction.
    A one-day spell reproduces v2 exactly for that day (same equation, same CN).
    """
    days = sorted(daily_mm)
    rain = [daily_mm[d] for d in days]
    cn_by_class = dict(zip(("I", "II", "III"), amc.curve_numbers()))
    out = {}
    in_spell = False
    dry_run = 0
    spell_age = 0
    Pc = 0.0
    Qprev = 0.0
    S = None
    for i, d in enumerate(days):
        wet = rain[i] >= wet_day_mm
        if in_spell and spell_age >= max_spell_days:
            in_spell = False
        if not in_spell:
            if not wet:
                out[d] = 0.0
                continue
            in_spell = True
            dry_run = 0
            spell_age = 0
            Pc = 0.0
            Qprev = 0.0
            antecedent = sum(rain[max(0, i - amc.ANTECEDENT_DAYS):i])
            cls = amc.amc_class(antecedent)
            if floor:
                cls = amc.apply_wet_season_floor(cls, d)
            S = amc.retention(cn_by_class[cls])
        Pc += rain[i]
        spell_age += 1
        Qc = cumulative_runoff(Pc, S, lam)
        out[d] = max(0.0, Qc - Qprev)
        Qprev = Qc
        if wet:
            dry_run = 0
        else:
            dry_run += 1
            if dry_run >= dry_break_days:
                in_spell = False
    return out


# ---------------------------------------------------------------------------
# Live use (supplementary advisory layer only)
# ---------------------------------------------------------------------------
import forecast
from datetime import date as _date

# Full 36-year replay validation of this supplementary model (floor on),
# scored exactly as the primary model: see V3_TEST_REPORT.md.
REPLAY_STATS = {
    "period": "1990-2025",
    "alert_days": 68,
    "false_alarm_days": 52,
    "episodes_caught": 4,
    "episodes_total": 6,
    "primary_alert_days": 12,
    "primary_false_alarm_days": 2,
    "primary_episodes_caught": 2,
    "occasions": 14,
    "occasions_flood_followed": 4,
    "occasions_no_flood": 10,
}


def _predicted_peak_today(eff_map, today):
    """Predicted peak (m3/s, incl. monthly baseflow) over the next 7 days from
    effective runoff up to and including today, assuming no further rain."""
    uh = forecast.unit_hydrograph()
    days = sorted(eff_map)
    i = days.index(today)
    best, best_k = 0.0, 0
    for k in range(forecast.HORIZON_DAYS + 1):
        t = i + k
        q = 0.0
        for j in range(max(0, t - len(uh) + 1), i + 1):
            u = t - j
            if u < len(uh) and eff_map[days[j]]:
                q += eff_map[days[j]] * uh[u]
        if q > best:
            best, best_k = q, k
    return best + forecast.MONTHLY_BASEFLOW[today.month], best_k


def live_model_v3(full_series, now_str, thresholds, advisory_discharge):
    """
    Supplementary cumulative-model block for live_data.json -> rainfall.model_v3.

    SUPPLEMENTARY BY DESIGN: this block is advisory only. It must never drive
    the dashboard headline level (that stays with the river reading and the
    primary forecast in forecast.live_model). It exists because in the
    36-year replay it caught 4 of 6 flood episodes against the primary
    model's 2 of 6, but with 52 false alarm days against the primary's 2,
    so its signals are shown as Advisory, not Watch.

    full_series / now_str / thresholds: same inputs as forecast.live_model.
    advisory_discharge: the Advisory design discharge (ews_data.json
    advisory_display, 1,357.7 m3/s), scaled to a forecast trigger with the
    same quickflow factor as the other levels.
    """
    observed = [p for p in full_series if p["t"] <= now_str]
    daily = amc.daily_totals(observed)
    today = _date.fromisoformat(now_str[:10])
    eff_floor = effective_runoff_series(daily, floor=True)
    eff_raw = effective_runoff_series(daily, floor=False)
    peak, lag = _predicted_peak_today(eff_floor, today)
    peak_raw, _ = _predicted_peak_today(eff_raw, today)
    trig = forecast.forecast_triggers(thresholds, today.month)
    base = forecast.MONTHLY_BASEFLOW[today.month]
    adv_trigger = base + forecast.QUICKFLOW_BIAS * (advisory_discharge - base)
    if peak >= trig["watch"]:
        signal = "watch-level signal (advisory only)"
    elif peak >= adv_trigger:
        signal = "advisory"
    else:
        signal = "none"
    return {
        "role": "supplementary, advisory only, never raises the headline level",
        "method": "Bounded cumulative SCS abstraction: Ia (20% of S) charged once per wet spell "
                  "(max 6 days, 1 dry day ends a spell) against cumulative rain, daily runoff "
                  "as increments of cumulative runoff; same unit hydrograph, baseflow and "
                  "forecast triggers as the primary model",
        "as_of": now_str,
        "today": today.isoformat(),
        "history_days": len(daily),
        "predicted_peak": round(peak, 1),
        "predicted_peak_without_floor": round(peak_raw, 1),
        "days_to_peak": lag,
        "signal": signal,
        "triggers": {"advisory": round(adv_trigger, 1),
                     "watch": round(trig["watch"], 1),
                     "warning": round(trig["warning"], 1),
                     "emergency": round(trig["emergency"], 1)},
        "validation": REPLAY_STATS,
    }
