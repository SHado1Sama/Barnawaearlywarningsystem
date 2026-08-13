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
