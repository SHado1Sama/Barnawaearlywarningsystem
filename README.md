# Barnawa Early Warning System

Historical replay and live-conditions dashboard for the Barnawa catchment
(Kaduna, Nigeria) flood early warning system. Static site, rebuilt every 30
minutes by GitHub Actions and served from GitHub Pages — no backend server.

## What it shows

- **Historical replay**: a 36-year (1990-2025) daily discharge record scrubbed
  against Advisory/Watch/Warning/Severe thresholds derived from a Gumbel
  (Extreme Value Type I) frequency analysis of the same record (R² = 0.94).
  Includes the full event log and two rainfall-to-peak lead-time case studies
  (2012, 2022).
- **Live conditions**: real rainfall (Open-Meteo, at the catchment's actual
  coordinates) checked against a 20mm/24h trigger, plus a discharge forecast
  from the nearest GEOGloWS-mapped river reach (~5.3km away, a materially
  smaller stream — shown only as a rough trend/percentile cross-check, never
  compared directly to the Barnawa thresholds).

## How the live refresh works

`.github/workflows/deploy.yml` runs on a 30-minute cron:

1. `live_fetch.py` — pulls rainfall (Open-Meteo) and discharge forecast
   (GEOGloWS v2), writes `live_data.json`. No API keys required.
2. `build_site.py` — embeds fonts, `ews_data.json` (historical, static) and
   `live_data.json` into `dashboard_template.html`, writes `dist/index.html`.
3. The `dist/` folder is deployed to GitHub Pages.

Pure Python standard library — no `pip install` step needed in CI.

## Antecedent moisture condition (AMC) and the wet-season floor

`amc.py` holds the soil-wetness logic from Section 3.7.2 of the report, the same
method used in the offline simulation: the rain that fell in the 5 complete days
before a day sets the condition (below 35 mm dry, 35 to 53 mm average, above
53 mm wet), which selects the SCS curve number (48.7 / 69.3 / 83.9) and the
initial abstraction (53.5 / 22.5 / 9.8 mm).

**Wet-season floor (correction for the 2012 miss).** From July to September the
soil is never treated as dry: if the 5-day rule gives AMC I in those months, AMC II
is used. Reason: on 24 Aug 2012, 97 mm of rain fell after only 31 mm in the previous
5 days. The dry class absorbed the first 53.5 mm, so the forecast peak (262 m3/s)
stayed below the Watch trigger (374 m3/s) and a real Watch-level flood (2,074 m3/s)
was missed. With the floor the same storm absorbs 22.5 mm and the forecast peak is
504 m3/s, above the trigger, three days before the observed peak. The change is
`WET_SEASON_MONTHS` and `apply_wet_season_floor()` in `amc.py`.

- `forecast.py` is the rainfall-driven forecast of the offline simulation without numpy
  (SCS curve number with the soil class above, daily unit hydrograph, monthly baseflow).
  It runs in two places: `build_site.py` replays the stored 2012 and 2022 seasons with and
  without the floor (the "Forecast check" in each case card), and `live_fetch.py` runs it on
  the live Open-Meteo rain (past 21 days, no future rain) and writes the result to
  `live_data.json` under `rainfall.model`. The dashboard shows it as the "Rainfall-driven
  forecast" card and, when it is higher than the river-flow reading, as the headline level
  marked "FORECAST". To keep the headline on the river-flow reading only, set
  `MODEL_RAISES_BANNER = false` in `dashboard_template.html`.
- **Triggers are baseflow-aware.** The earlier forecast triggers were the design flows times
  0.2038 (Watch 374 m3/s in every month), but baseflow is added to the forecast at its true
  value. September baseflow (341 m3/s) is 91% of 374, so ordinary rain gave 13 false-alarm
  days in 2022. Now: trigger = baseflow(month) + k x (design flow - baseflow(month)), with
  k = (711.4 - 199.6) / (3496.9 - 199.6) = 0.155 from the 2004 calibration event. Watch is
  342 m3/s in July, 454 in August, 573 in September. Set `BASEFLOW_AWARE_TRIGGERS = False`
  in `forecast.py` to go back to the earlier triggers.
- `live_fetch.py` also adds the current soil condition under `rainfall.amc`, shown in the
  rainfall card.
- Check everything with `python test_amc.py`.

Limits: rainfall is one grid cell near the catchment, so values are indicative. The replay
covers two of the 36 seasons: it shows the 2012 miss is corrected (504 against a 454 m3/s
August trigger) and that neither season has false-alarm days, but it is not a detection
rate. The rainfall-driven forecast is experimental until the full 36-year replay (the
offline simulation with the ERA5 rainfall file) has been run with the same rules.


## Two models: primary forecast and a supplementary cumulative model

The dashboard runs two rainfall-driven forecasts side by side:

- **Primary (forecast.py)** decides the headline level together with the river
  reading. Per-day SCS curve number with the AMC soil classes and the
  wet-season floor above. On the full 36-year replay (rainfall file
  rain_windows.csv, box-averaged ERA5, scored against the observed record):
  12 alert days, 2 false alarm days (both trailing a real flood), and 2 of
  the 6 flood episodes caught (2004 and 2012). It is conservative and
  rarely wrong, but it misses floods that build from many moderate rain
  days, because each day is charged the full initial abstraction again.
- **Supplementary (cumulative.py)**, advisory only, and **experimental: it is a
  post-defence extension, not part of the defended project report.** It was
  designed after studying why the recorded floods were missed, and then scored
  on that same record, so its figures below are a design check, not a proven
  detection rate; only future flood seasons can test it. It charges the initial
  abstraction (Ia = 20% of S) once per wet spell against the spell's
  cumulative rain and takes each day's runoff as the increment of
  cumulative runoff (the procedure NEH Part 630 uses to spread runoff
  through a storm), with spells capped at 6 days. On the same replay:
  68 alert days, 52 false alarm days, and 4 of 6 episodes caught (1999,
  2004, 2012, 2014; it still misses 2008 and 2024). Grouped into occasions,
  its signal fired 14 times in 36 years: a flood followed 4 times, and 10
  times no flood followed. The settings are not magic: across spell caps of
  4, 6 and 8 days and dry gaps of 1 and 2 days it catches 2, 4 and 5 of 6
  with false days rising alongside (26, 52, 100 at gap 1), so 6 days and
  1 day is a middle point on a smooth trade, and at cap 6 the 2014 catch
  depends on the 1-day gap. It catches more floods but cries wolf far too often
  to issue warnings, so on the dashboard it can only ever show an
  **Advisory**: it never raises the headline level. Treat its signal as a
  prompt to watch the river, not as a warning. Neither model catches the
  2024 episode on this rainfall; see the replay notes in the project
  record before quoting detection rates.

Checks: `python test_amc.py` for the primary model's soil and forecast
logic, `python test_cumulative.py` for the supplementary model.

## Local development

```bash
python live_fetch.py     # writes live_data.json
python build_site.py     # writes dist/index.html
python -m http.server --directory dist 8000
```

## Regenerating the historical dataset

`ews_data.json` is static (the 36-year record doesn't change). It was produced
by `ews_analysis.py` in the parent project from the original streamflow and
rainfall CSVs — that script isn't part of this repo since it depends on the
full source data, but the output JSON schema is documented at the top of
`dashboard_template.html`'s inline script.
