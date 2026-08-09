"""
Collect all sources, run the calculations, write data/latest.json.

This is what GitHub Actions runs on a schedule. The Streamlit dashboard
only ever reads the file this produces - it makes no network requests.

Exit code 0 = success, 1 = failure (leaves the previous file untouched).
"""

import json
import sys
from datetime import datetime, timezone

import pandas as pd

import config
from src.calculations import agreement, rolling
from src.sources import bom_forecast, openmeteo

MAX_PLAUSIBLE_24H_MM = 1000.0


def now_utc():
    return datetime.now(timezone.utc)


def iso(timestamp):
    return None if timestamp is None else timestamp.isoformat(timespec="seconds")


def local(timestamp):
    return timestamp.tz_convert(config.LOCAL_TZ)


def clean(value, digits=2):
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def validate(summary):
    problems = []
    if summary.empty:
        problems.append("no complete 24-hour windows")
        return problems
    if (summary["mean"] < 0).any():
        problems.append("negative rainfall in ensemble mean")
    if (summary["max"] > MAX_PLAUSIBLE_24H_MM).any():
        problems.append(f"24-hour total above {MAX_PLAUSIBLE_24H_MM:.0f} mm")
    if (summary["p10"] > summary["p90"]).any():
        problems.append("P10 above P90")
    return problems


def source_record(result, extra=None):
    record = {
        "status": result["status"],
        "label": result["label"],
        "retrieved_at_utc": result["retrieved_at_utc"],
    }
    if result["status"] != "ok":
        record["error"] = result["error"]
        return record

    record["model_run_utc"] = result.get("model_run_utc")
    for key in ("centre", "model_id", "grid_point", "units", "note",
                "member_count", "valid_steps", "source_url", "location"):
        if key in result:
            record[key] = result[key]
    if extra:
        record.update(extra)
    return record


def main():
    started = now_utc()
    print(f"Collection started {started.isoformat(timespec='seconds')}")

    sources = {}

    ensemble = openmeteo.fetch_ensemble()
    sources["ecmwf_ensemble"] = source_record(ensemble)
    if ensemble["status"] != "ok":
        print(f"FATAL: ensemble unavailable - {ensemble['error']}")
        print("Not writing output. Previous data left in place.")
        return 1
    print(f"  ok      {ensemble['label']} "
          f"({ensemble['member_count']} members)")

    accumulated = rolling.accumulate(ensemble["frame"])
    summary = rolling.ensemble_summary(accumulated)

    problems = validate(summary)
    if problems:
        print(f"FATAL: validation failed - {'; '.join(problems)}")
        print("Not writing output. Previous data left in place.")
        return 1

    peak = rolling.peak_window(summary["mean"])
    peak_stats = summary.loc[peak["end"]]
    member_fraction = peak_stats["members_over"] / peak_stats["members_total"]

    entries = [agreement.build_entry(ensemble["label"], peak,
                                     member_fraction=member_fraction)]
    deterministic = {}

    for result in openmeteo.fetch_all_deterministic():
        key = result["label"].lower()
        if result["status"] != "ok":
            sources[key] = source_record(result)
            entries.append(agreement.build_entry(result["label"], None))
            print(f"  FAILED  {result['label']} - {result['error']}")
            continue

        series = rolling.accumulate(result["frame"]).iloc[:, 0]
        deterministic[result["label"]] = series

        value = series.get(peak["end"])
        covers = value is not None and not pd.isna(value)

        sources[key] = source_record(result, {"covers_peak_window": covers})
        entries.append(agreement.build_entry(
            result["label"], rolling.peak_window(series),
            covers_window=covers))
        print(f"  ok      {result['label']} ({result['valid_steps']} steps)")

    bom = bom_forecast.fetch()
    sources["bom_detailed"] = source_record(bom, {
        "days_found": bom.get("days_found"),
        "steps_found": bom.get("steps_found"),
        "steps_with_amounts": bom.get("steps_with_amounts"),
        "usage_note": bom.get("usage_note"),
    })
    if bom["status"] == "ok":
        print(f"  ok      {bom['label']} ({bom['steps_found']} steps)")
    else:
        print(f"  FAILED  {bom['label']} - {bom['error']}")

    verdict = agreement.classify(entries)
    status = agreement.headline_status(peak_stats, verdict["level"])

    daily = []
    for row in rolling.daily_windows(summary, deterministic):
        start_local = local(row["window_start"])
        end_local = local(row["window_end"])
        daily.append({
            "window_start_local": start_local.isoformat(),
            "window_end_local": end_local.isoformat(),
            "day_label": f"{start_local:%a %d %b}",
            "window_label": f"{start_local:%H:%M} \u2192 {end_local:%H:%M}",
            "ecmwf_mean": row["mean"],
            "ecmwf_p10": row["p10"],
            "ecmwf_p90": row["p90"],
            "members_over": row["members_over"],
            "members_total": row["members_total"],
            "percent_over": row["percent_over"],
            "models": row["models"],
        })

    curve = []
    for index, row in summary.iterrows():
        models = {label: clean(series.get(index))
                  for label, series in deterministic.items()}
        curve.append({
            "window_end_local": local(index).isoformat(),
            "mean": clean(row["mean"]),
            "p10": clean(row["p10"]),
            "p90": clean(row["p90"]),
            "models": models,
        })

    payload = {
        "generated_at_utc": iso(started.replace(microsecond=0)),
        "generated_at_local": local(pd.Timestamp(started)).isoformat(
            timespec="seconds"),
        "location": {
            "name": config.LOCATION_NAME,
            "latitude": config.LATITUDE,
            "longitude": config.LONGITUDE,
            "timezone": config.LOCAL_TZ,
        },
        "threshold_mm": config.THRESHOLD_MM,
        "window_hours": config.WINDOW_HOURS,
        "window_mode": config.DAILY_WINDOW_MODE,
        "rain_day_start_hour": config.RAIN_DAY_START_HOUR,
        "attribution": config.ATTRIBUTION,
        "headline": {
            "status_code": status["code"],
            "status_text": status["text"],
            "window_start_local": local(peak["start"]).isoformat(),
            "window_end_local": local(peak["end"]).isoformat(),
            "ecmwf_mean": round(float(peak_stats["mean"]), 1),
            "ecmwf_p10": round(float(peak_stats["p10"]), 1),
            "ecmwf_p90": round(float(peak_stats["p90"]), 1),
            "members_over": int(peak_stats["members_over"]),
            "members_total": int(peak_stats["members_total"]),
            "percent_over": int(peak_stats["percent_over"]),
        },
        "agreement": verdict,
        "daily_comparison": daily,
        "rolling_curve": curve,
        "bom_forecast": {
            "status": bom["status"],
            "rows": bom.get("rows", []),
            "source_url": bom.get("source_url"),
        },
        "sources": sources,
        "reference_links": config.REFERENCE_LINKS,
        "unavailable_models": config.UNAVAILABLE_MODELS,
    }

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.LATEST_FILE.write_text(json.dumps(payload, indent=2),
                                  encoding="utf-8")

    size_kb = config.LATEST_FILE.stat().st_size / 1024
    print(f"\n  {status['text']}")
    print(f"  {local(peak['start']):%a %d %b %H:%M} -> "
          f"{local(peak['end']):%a %d %b %H:%M} AEST")
    print(f"  mean {peak_stats['mean']:.1f} mm, "
          f"P10-P90 {peak_stats['p10']:.1f}-{peak_stats['p90']:.1f} mm")
    print(f"  agreement: {verdict['level']}")
    print(f"  daily table: {config.DAILY_WINDOW_MODE} "
          f"({len(daily)} columns)")
    print(f"\n  Wrote {config.LATEST_FILE} ({size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())