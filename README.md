# Gold Coast Rainfall Dashboard

Operational dashboard answering one question:

> Is there likely to be at least 10 mm of rainfall over any 24-hour period
> at Gold Coast Airport, and should fieldwork be mobilised?

## How it works

    collect.py  ->  data/latest.json  ->  app.py

`collect.py` runs on a schedule via GitHub Actions. It fetches every source,
runs the calculations, and writes a single JSON file. The Streamlit dashboard
reads that file and nothing else - it makes no network requests and performs
no calculations, so opening it is instant and unaffected by source outages.

## Data sources

| Source | Centre | Role |
|---|---|---|
| ECMWF IFS 0.25 ensemble, 51 members | ECMWF | Primary. Uncertainty range. |
| GFS | NOAA, United States | Independent check |
| UKMO global 10 km | Met Office, United Kingdom | Independent check |
| ICON global | DWD, Germany | Independent check |
| Coolangatta detailed forecast | BOM | Display only, near term |

Forecast data via Open-Meteo (CC BY 4.0). BOM forecast scraped from the
public page.

ECMWF's deterministic run is deliberately excluded. It shares a centre and a
model with the ensemble, so counting it would inflate apparent agreement.

## The rolling 24-hour calculation

Hourly precipitation is accumulated over every possible 24-hour window at
hourly steps - not calendar-day totals. The headline reports the window with
the highest ensemble mean, searched across all start hours.

The daily tables use fixed 09:00 to 09:00 AEST rain days so columns are
comparable. An event straddling 09:00 can split across two columns and read
lower than the headline; the headline is authoritative.

## Model agreement

Categorical, never a numeric score. A source indicates an event when its peak
24-hour total reaches 10 mm, or - for the ensemble - when at least 25% of
members do. The ensemble counts as one source, not 51.

- **strong** - two or more sources indicate, windows within 12 hours, largest
  amount no more than twice the smallest
- **moderate** - two or more indicate, but timing or magnitude differs
- **weak** - exactly one indicates
- **none** - no source indicates

The reasoning behind every classification is shown on the dashboard.

## Known limitations

**Grid points are not the airport.** Global models hold values at grid cell
centres 7-18 km away, scattered inland. Acceptable for a 24-hour regional
rainfall question; less so for a single convective cell.

**BOM amounts extend about 48 hours.** Beyond that BOM publishes only chance
of any rain.

**BOM exceedance amounts are quantiles, not totals.** "50% chance of more
than 4 mm" cannot be added to the next 3-hour block. BOM is displayed as
published and feeds no calculation.

**Member fractions are not probabilities.** "13 of 51 members reached 10 mm"
is a fact about the model. Ensembles are under-dispersive for rainfall, so it
is not a calibrated chance of rain.

## Sources investigated and not used

| Source | Why not |
|---|---|
| ACCESS-C (BN) | Raw NWP requires a paid BOM Registered User subscription |
| ACCESS-G | Open-Meteo returns only nulls at this location on all routes |
| Boyd St gauge 540842 | Under `/fwo/`, disallowed by BOM robots.txt. Link only. |
| AWO soil moisture | JavaScript application, no verified point-query route |
| Meteologix ensemble | Charts are images; no numeric data to extract |
| OzForecast | `/cgi-bin/` disallowed by robots.txt. Same NOAA GFS data used directly. |

ACCESS-G can be restored by moving its entry from `UNAVAILABLE_MODELS` to
`DETERMINISTIC_MODELS` in `config.py`. Nothing else needs to change.

## Running locally

    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt
    python collect.py
    streamlit run app.py

## Configuration

Everything adjustable lives in `config.py`: location, the 10 mm threshold,
model list, forecast horizon, daily window convention, map basemap.

`ENSEMBLE_MEMBER_FRACTION` in `src/calculations/agreement.py` sets how many
members must reach the threshold for the ensemble to count as indicating an
event. Currently 25%.