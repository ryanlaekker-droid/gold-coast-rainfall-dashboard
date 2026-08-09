"""
BOM Coolangatta detailed forecast (beta).

Extracts only the rainfall block: chance of any rain, and the 50%, 25% and
10% exceedance amounts, in 3-hourly steps. Nothing else from the page.

Display only. These figures never feed the rolling 24-hour calculation.
Exceedance amounts are quantiles, not totals, so they cannot be summed
across time steps to produce a 24-hour figure.
"""

import re
from datetime import datetime, timezone
from io import StringIO

import pandas as pd
import requests

import config

URL = "https://www.bom.gov.au/places/qld/coolangatta/forecast/detailed/"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-AU,en;q=0.9",
}

TIMEOUT = 30

ROW_LABELS = {
    "chance of any rain": "chance_any_rain",
    "50% chance of more than": "mm_50pct",
    "25% chance of more than": "mm_25pct",
    "10% chance of more than": "mm_10pct",
}

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}


def _now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _failed(error):
    return {
        "status": "failed",
        "label": "BOM detailed forecast",
        "error": str(error)[:200],
        "retrieved_at_utc": _now_utc(),
        "source_url": URL,
        "rows": [],
    }


def _clean_label(text):
    return re.sub(r"\s*\(.*?\)\s*", " ", str(text)).strip().lower()


def _clean_value(text):
    value = str(text).strip().replace("%", "")
    if value in ("", "-", "\u2013", "\u2014", "nan", "None"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _timestamp(day_label, time_label, reference):
    """'Sunday 9 August' + '1:00 AM' -> a local timestamp.

    The page gives no year, so it is taken from the current date, with a
    guard for the December-January rollover.
    """
    day_match = re.search(r"(\d{1,2})\s+([A-Za-z]+)", str(day_label))
    time_match = re.match(r"\s*(\d{1,2}):(\d{2})\s*([AaPp])",
                          str(time_label))
    if not day_match or not time_match:
        return None

    month = MONTHS.get(day_match.group(2).lower())
    if month is None:
        return None

    hour = int(time_match.group(1)) % 12
    if time_match.group(3).lower() == "p":
        hour += 12

    year = reference.year
    if month < reference.month - 6:
        year += 1
    elif month > reference.month + 6:
        year -= 1

    try:
        return pd.Timestamp(year=year, month=month, day=int(day_match.group(1)),
                            hour=hour, minute=int(time_match.group(2)),
                            tz=config.LOCAL_TZ)
    except Exception:
        return None


def _is_rainfall_table(frame):
    labels = {_clean_label(v) for v in frame.iloc[:, 0]}
    return any(key in labels for key in ROW_LABELS)


def _parse_table(frame, day_label, reference):
    times = [str(c).strip() for c in frame.columns[1:]]
    records = []
    for label in times:
        moment = _timestamp(day_label, label, reference)
        records.append({
            "day": day_label,
            "time": label,
            "timestamp_local": None if moment is None else moment.isoformat(),
        })

    for _, row in frame.iterrows():
        key = ROW_LABELS.get(_clean_label(row.iloc[0]))
        if key is None:
            continue
        for position, value in enumerate(row.iloc[1:]):
            if position < len(records):
                records[position][key] = _clean_value(value)

    return [r for r in records if any(k in r for k in ROW_LABELS.values())]


def _day_headings(html):
    pattern = r"<h2[^>]*>\s*([A-Z][a-z]+day\s+\d{1,2}\s+[A-Z][a-z]+)\s*</h2>"
    return re.findall(pattern, html)


def fetch():
    try:
        response = requests.get(URL, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
        html = response.text
    except Exception as error:
        return _failed(error)

    try:
        tables = pd.read_html(StringIO(html))
    except Exception as error:
        return _failed(f"could not parse tables: {str(error)[:120]}")

    rainfall_tables = [t for t in tables if _is_rainfall_table(t)]
    if not rainfall_tables:
        return _failed("no rainfall table found - page layout may have changed")

    reference = pd.Timestamp.now(tz=config.LOCAL_TZ)
    days = _day_headings(html)
    rows = []
    for position, table in enumerate(rainfall_tables):
        label = days[position] if position < len(days) else f"day {position + 1}"
        rows.extend(_parse_table(table, label, reference))

    if not rows:
        return _failed("rainfall table found but contained no usable rows")

    with_amounts = sum(1 for r in rows if r.get("mm_50pct") is not None)
    with_times = sum(1 for r in rows if r.get("timestamp_local"))

    return {
        "status": "ok",
        "label": "BOM detailed forecast",
        "source_url": URL,
        "location": "Coolangatta",
        "retrieved_at_utc": _now_utc(),
        "model_run_utc": None,
        "days_found": len(rainfall_tables),
        "steps_found": len(rows),
        "steps_with_amounts": with_amounts,
        "steps_with_times": with_times,
        "usage_note": ("Display only. Exceedance amounts are quantiles and "
                       "cannot be summed to a 24-hour total."),
        "rows": rows,
    }