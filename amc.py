"""
Barnawa EWS - antecedent moisture condition (AMC) logic.

This is the same method described in Section 3.7.2 of the project report and
used in the offline Python simulation (barnawa_ews.py), written with the
standard library only so the GitHub Actions runner needs nothing extra.

Method (SCS curve number, USDA-NRCS 1986):
  1. Add up the rain that fell on the 5 complete days BEFORE the day in question
     (the 5-day antecedent precipitation, current day excluded).
  2. Pick the soil condition from that total:
         below 35 mm        AMC I   (dry)
         35 to 53 mm        AMC II  (average)
         above 53 mm        AMC III (wet)
  3. Use the matching curve number (CN I, CN II, CN III). CN I and CN III are
     obtained from the calibrated CN II by the standard conversion of
     Chow, Maidment and Mays (1988).
  4. Convert rainfall to runoff:
         S  = 25400 / CN - 254            potential maximum retention (mm)
         Ia = 0.2 * S                     initial abstraction (mm)
         Q  = (P - Ia)^2 / (P - Ia + S)   for P > Ia, otherwise 0 (mm)

With CN II = 69.321 this gives CN 48.7 / 69.3 / 83.9 and Ia 53.5 / 22.5 / 9.8 mm,
the values quoted in the report.

Wet-season floor (correction to the forecast, added after the 2012 miss):
  From July to September the ground is rarely truly dry. If the 5-day rule says
  AMC I (dry) in one of those months, AMC II (average) is used instead. Nothing
  else changes. On 24 Aug 2012, 97 mm fell after only 31 mm in the previous 5
  days; the dry class absorbed the first 54 mm and the forecast peak stayed
  below the Watch trigger, while the floor lifts it above the trigger.
"""
from datetime import date, datetime, timedelta

CN_II = 69.321            # calibrated average-condition curve number (report, Section 4.2)
DRY_BELOW_MM = 35.0       # 5-day antecedent rain below this: dry (AMC I)
WET_ABOVE_MM = 53.0       # 5-day antecedent rain above this: wet (AMC III)
ANTECEDENT_DAYS = 5
WET_SEASON_MONTHS = (7, 8, 9)   # July, August, September: soil is never treated as dry

_NAMES = {"I": "dry", "II": "average", "III": "wet"}


def curve_numbers(cn2=CN_II):
    """Return (CN I, CN II, CN III) from the calibrated CN II (Chow et al., 1988)."""
    cn1 = 4.2 * cn2 / (10 - 0.058 * cn2)
    cn3 = 23.0 * cn2 / (10 + 0.130 * cn2)
    return cn1, cn2, cn3


def amc_class(antecedent_mm):
    """Return 'I', 'II' or 'III' for a 5-day antecedent rainfall total in mm."""
    if antecedent_mm < DRY_BELOW_MM:
        return "I"
    if antecedent_mm <= WET_ABOVE_MM:
        return "II"
    return "III"


def apply_wet_season_floor(cls, day):
    """Wet-season floor: AMC I becomes AMC II in July, August and September."""
    if cls == "I" and day.month in WET_SEASON_MONTHS:
        return "II"
    return cls


def retention(cn):
    """Potential maximum retention S in mm."""
    return 25400.0 / cn - 254.0


def initial_abstraction(cn):
    """Initial abstraction Ia = 0.2 * S in mm."""
    return 0.2 * retention(cn)


def runoff_mm(rain_mm, cn):
    """SCS direct runoff depth (mm) for a rainfall depth (mm) and curve number."""
    s = retention(cn)
    excess = rain_mm - 0.2 * s
    if excess <= 0:
        return 0.0
    return excess * excess / (excess + s)


def antecedent_total(daily_mm, day):
    """
    Sum of rainfall over the 5 complete days before `day`.
    daily_mm: dict mapping datetime.date -> rainfall in mm.
    Returns (total_mm, days_found). days_found < 5 means some days had no data.
    """
    total, found = 0.0, 0
    for k in range(1, ANTECEDENT_DAYS + 1):
        d = day - timedelta(days=k)
        if d in daily_mm:
            total += daily_mm[d]
            found += 1
    return total, found


def describe(daily_mm, day, cn2=CN_II, wet_season_floor=True):
    """
    Full AMC description for one day: class, curve number, losses.
    'amc_raw' is the class from the 5-day rule alone; 'amc' is the class used
    (after the wet-season floor, unless wet_season_floor=False).
    """
    total, found = antecedent_total(daily_mm, day)
    raw = amc_class(total)
    cls = apply_wet_season_floor(raw, day) if wet_season_floor else raw
    cn = dict(zip(("I", "II", "III"), curve_numbers(cn2)))[cls]
    return {
        "date": day.isoformat(),
        "antecedent_5d_mm": round(total, 1),
        "days_found": found,
        "window_from": (day - timedelta(days=ANTECEDENT_DAYS)).isoformat(),
        "window_to": (day - timedelta(days=1)).isoformat(),
        "amc": cls,
        "amc_raw": raw,
        "floor_applied": cls != raw,
        "condition": _NAMES[cls],
        "cn": round(cn, 1),
        "s_mm": round(retention(cn), 1),
        "ia_mm": round(initial_abstraction(cn), 1),
    }


def daily_totals(hourly_points):
    """
    Turn hourly points [{'t': 'YYYY-MM-DDTHH:MM', 'mm': x}, ...] into
    {date: total_mm} by UTC calendar day.
    """
    out = {}
    for p in hourly_points:
        d = date.fromisoformat(p["t"][:10])
        out[d] = out.get(d, 0.0) + (p["mm"] or 0.0)
    return out


def build_live_amc(full_series, today, trigger_time=None, trigger_rain_24h_mm=None, rain_24h_mm=0.0):
    """
    Build the 'amc' block written to live_data.json.

    full_series         hourly points (past 7 days observed + 7 days forecast)
    today               today's UTC date (datetime.date)
    trigger_time        'YYYY-MM-DDTHH:MM' of the 20 mm / 24 h trigger, or None
    trigger_rain_24h_mm trailing 24 h rainfall at the trigger hour
    rain_24h_mm         trailing 24 h rainfall right now
    """
    daily = daily_totals(full_series)
    now = describe(daily, today)
    now["rain_24h_mm"] = round(rain_24h_mm, 1)
    now["runoff_24h_mm"] = round(runoff_mm(rain_24h_mm, now["cn"]), 1)

    trig = None
    if trigger_time:
        # The trigger fires when the trailing 24 h total reaches 20 mm, so the storm began
        # about 23 h earlier. The antecedent days are counted before that start date, so the
        # storm's own rain is never counted as "antecedent".
        storm_start = datetime.fromisoformat(trigger_time) - timedelta(hours=23)
        trig = describe(daily, storm_start.date())
        trig["time"] = trigger_time
        trig["storm_start"] = storm_start.strftime("%Y-%m-%dT%H:%M")
        p = trigger_rain_24h_mm if trigger_rain_24h_mm is not None else 0.0
        trig["rain_24h_mm"] = round(p, 1)
        trig["runoff_24h_mm"] = round(runoff_mm(p, trig["cn"]), 1)

    return {
        "method": "SCS curve number with 5-day antecedent rainfall (report Section 3.7.2)",
        "dry_below_mm": DRY_BELOW_MM,
        "wet_above_mm": WET_ABOVE_MM,
        "wet_season_months": list(WET_SEASON_MONTHS),
        "now": now,
        "trigger": trig,
    }
