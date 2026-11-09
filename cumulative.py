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
cumulative runoff, the procedure NRCS sets out for runoff during a storm
in the National Engineering Handbook, Part 630, Chapter 10, section
630.1002(c), worked as Example 10-6 ("tabulate the accumulated rainfalls,
estimate the accumulated runoff, compute the increments of runoff").
Scope note: NRCS applies that procedure WITHIN a single storm. Extending
it across the days of a wet spell, and the bounds below (6-day cap, 1-day
dry break), are this project's own heuristics, not NRCS method:
    Pc(t) = rain accumulated since the spell began
    Qc(t) = (Pc - Ia)^2 / (Pc - Ia + S)  for Pc > Ia, else 0
    runoff(t) = Qc(t) - Qc(t-1)

The bound (what makes this v3 rather than the rejected raw version):
  - A spell is at most MAX_SPELL_DAYS = 6 days: the storm day plus the same
    5 antecedent days the AMC logic already uses as the soil's memory.
    After 6 days a new spell starts and Ia is charged again.
  - A spell also ends after DRY_BREAK_DAYS = 1 day with rain below
    WET_DAY_MM = 1.0 mm.
  - The curve number is FIXED at CN II (the AMC average-condition
    value) for every spell: no AMC classification and no wet-season
    floor in this model (the primary model keeps both). Revision of
    9 Nov 2026, Addendum 6 of the test report: in the original design
    each spell took the AMC class of the 5 days before it, so a spell
    starting on wet ground ran at CN III, whose small retention made
    six days of compounding explode into false peaks. Fixing CN II
    kept every catch on both test records and cut the false alarm
    days by half to two thirds.
  - lambda stays 0.20, the value the published CN set was built with.

Everything downstream is v2 unchanged: unit hydrograph, monthly baseflow,
baseflow-aware triggers, classification.

Honest status, from the full 36-year test (V3_TEST_REPORT.md in this
repo): at the Watch trigger it catches 4 of 6 observed flood episodes
(v2: 2 of 6) at 43 alert days with 27 false alarm days (v2: 12 and 2);
at the Advisory trigger, the level this card actually signals, it
catches 5 of 6 (only 2024 missed) at 115 alert days in 21 occasions.
That replay runs on the archive rainfall series stored in this repo
(rain_era5_redownload_1990_2025.csv). The six flood years were later
re-settled on rainfall downloaded directly from the Copernicus
Climate Data Store (Addenda 5 and 6 of the test report): for 1999 to
2014 the two series agree to within 0.65 mm on any day, but the
archive series understates 2024 rainfall by about a third, and on
the direct rainfall both models catch 2024. Across the six flood
years on the direct rainfall this model catches 6 of 6 at the
Advisory trigger (18 false alarm days) and 5 of 6 at the Watch
trigger (7 false alarm days, and no false occasion: every Watch
signal cluster was followed by a real Watch-level flow), and v2
catches 3 of 6 (3 false alarm days). It is a detection-first
experimental variant, not a replacement for v2.
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


def effective_runoff_series(daily_mm, lam=LAMBDA,
                            dry_break_days=DRY_BREAK_DAYS,
                            max_spell_days=MAX_SPELL_DAYS,
                            wet_day_mm=WET_DAY_MM):
    """
    daily_mm: {date: rain mm} (any subset; processed in date order).
    Returns {date: runoff mm for that day} under bounded cumulative abstraction.
    The curve number is fixed at CN II for every spell (revised design,
    9 Nov 2026): this model does not use the AMC classes or the
    wet-season floor. A one-day spell therefore gives exactly the SCS
    runoff of that day's rain at CN II.
    """
    days = sorted(daily_mm)
    rain = [daily_mm[d] for d in days]
    S = amc.retention(amc.curve_numbers()[1])
    out = {}
    in_spell = False
    dry_run = 0
    spell_age = 0
    Pc = 0.0
    Qprev = 0.0
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

# Full 36-year replay validation of this supplementary model,
# scored exactly as the primary model: see V3_TEST_REPORT.md. The replay
# runs on the archive rainfall series stored in this repo; the separate
# flood_years_cds block below re-settles the six flood years on direct
# Copernicus CDS rainfall.
REPLAY_STATS = {
    "period": "1990-2025",
    # Occasions are clusters of alert days, split when the gap between
    # alert days exceeds 2 days.
    "watch_tier": {
        "alert_days": 43, "false_alarm_days": 27,
        "occasions": 9, "occasions_flood_followed": 4, "occasions_no_flood": 5,
        "episodes_caught": 4, "episodes_total": 6, "missed": "2008 and 2024",
    },
    "advisory_tier": {
        "alert_days": 115, "occasions": 21,
        "years_with_signal": 17, "mostly_month": "August",
        "episodes_caught": 5, "episodes_total": 6, "missed": "2024",
        "occasions_followed_by_advisory_flow": 11,
        "occasions_below_advisory": 10, "of_those_rose_1000_to_advisory": 4,
        "advisory_flow_m3s": 1357.7,
    },
    "primary_alert_days": 12,
    "primary_false_alarm_days": 2,
    "primary_episodes_caught": 2,
    # The six flood years re-settled on rainfall downloaded directly
    # from the Copernicus Climate Data Store (Nov 2026), scored year by
    # year with the same rules (see flood_years_cds.py and Addenda 5
    # and 6 of V3_TEST_REPORT.md; Addendum 5 settled the rainfall and
    # scored the original AMC-based design, Addendum 6 scores this
    # revised fixed-CN design). For 1999-2014 the direct series and the
    # archive series above agree to within 0.65 mm on any day; the
    # archive series understates 2024 by about a third, which is why
    # the episode counts differ from the 36-year replay.
    "flood_years_cds": {
        "source": "Copernicus CDS ERA5, direct download",
        "settled": "2026-11",
        "years": [1999, 2004, 2008, 2012, 2014, 2024],
        "episodes_total": 6,
        "advisory_episodes_caught": 6,
        "advisory_false_alarm_days": 18,
        "watch_episodes_caught": 5, "watch_missed": "2008",
        "watch_false_alarm_days": 7,
        "primary_episodes_caught": 3, "primary_false_alarm_days": 3,
    },
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
    model's 2 of 6, but with 27 false alarm days against the primary's 2
    at the Watch trigger, so its signals are shown as Advisory, not Watch.
    The card prints the record for the Advisory trigger it signals at,
    with the Watch-trigger record as a secondary line.

    full_series / now_str / thresholds: same inputs as forecast.live_model.
    advisory_discharge: the Advisory design discharge (ews_data.json
    advisory_display, 1,357.7 m3/s), scaled to a forecast trigger with the
    same quickflow factor as the other levels.
    """
    observed = [p for p in full_series if p["t"] <= now_str]
    daily = amc.daily_totals(observed)
    today = _date.fromisoformat(now_str[:10])
    eff = effective_runoff_series(daily)
    peak, lag = _predicted_peak_today(eff, today)
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
                  "as increments of cumulative runoff, curve number fixed at the AMC II value "
                  "for every spell (no AMC switching, no wet-season floor in this model); "
                  "same unit hydrograph, baseflow and forecast triggers as the primary model",
        "as_of": now_str,
        "today": today.isoformat(),
        "history_days": len(daily),
        "predicted_peak": round(peak, 1),
        "days_to_peak": lag,
        "signal": signal,
        "triggers": {"advisory": round(adv_trigger, 1),
                     "watch": round(trig["watch"], 1),
                     "warning": round(trig["warning"], 1),
                     "emergency": round(trig["emergency"], 1)},
        "validation": REPLAY_STATS,
    }
