"""
Rolling 24-hour rainfall accumulation.

Open-Meteo reports hourly precipitation as the total for the hour ENDING at
the given timestamp. A 24-row window ending at time T therefore covers the
period (T minus 24 hours) through to T.

No network access, no file access. Pure functions only.
"""

import pandas as pd

import config


def accumulate(frame, hours=None):
    """Total the previous N hours at every hourly step, per column."""
    hours = hours or config.WINDOW_HOURS
    return frame.rolling(window=hours, min_periods=hours).sum()


def ensemble_summary(accumulated):
    """Collapse per-member accumulations into statistics per window."""
    member_count = accumulated.shape[1]

    summary = pd.DataFrame({
        "mean": accumulated.mean(axis=1),
        "p10": accumulated.quantile(0.10, axis=1),
        "p90": accumulated.quantile(0.90, axis=1),
        "min": accumulated.min(axis=1),
        "max": accumulated.max(axis=1),
        "members_over": (accumulated >= config.THRESHOLD_MM).sum(axis=1),
    })
    summary["members_total"] = member_count
    summary["percent_over"] = (
        summary["members_over"] / member_count * 100).round(0)

    return summary.dropna(subset=["mean"])


def peak_window(series):
    """The window with the highest value. None if there is no usable data.

    This searches every hourly start time, which is what makes the headline
    a true rolling maximum rather than a calendar-day total.
    """
    usable = series.dropna()
    if usable.empty:
        return None

    end = usable.idxmax()
    return {
        "start": end - pd.Timedelta(hours=config.WINDOW_HOURS),
        "end": end,
        "value": float(usable.loc[end]),
    }


def _row(summary, deterministic, end):
    stats = summary.loc[end]
    start = end - pd.Timedelta(hours=config.WINDOW_HOURS)

    models = {}
    for label, series in deterministic.items():
        value = series.get(end)
        models[label] = None if value is None or pd.isna(value) \
            else round(float(value), 1)

    return {
        "window_start": start,
        "window_end": end,
        "mean": round(float(stats["mean"]), 1),
        "p10": round(float(stats["p10"]), 1),
        "p90": round(float(stats["p90"]), 1),
        "members_over": int(stats["members_over"]),
        "members_total": int(stats["members_total"]),
        "percent_over": int(stats["percent_over"]),
        "models": models,
    }


def rain_day_windows(summary, deterministic):
    """Fixed 09:00 to 09:00 AEST windows, one per rain day.

    Every column covers the same clock hours, so days are directly
    comparable and a window is always labelled by the day it starts.
    """
    local_index = summary.index.tz_convert(config.LOCAL_TZ)
    mask = ((local_index.hour == config.RAIN_DAY_START_HOUR)
            & (local_index.minute == 0))
    return [_row(summary, deterministic, end) for end in summary.index[mask]]


def peak_daily_windows(summary, deterministic):
    """The wettest window ending each local day.

    More sensitive than rain days, but the end time floats, so a window
    ending at 00:00 is labelled with the following day despite covering
    the previous one.
    """
    rows = []
    local_end = summary.index.tz_convert(config.LOCAL_TZ)
    for _, group in summary.groupby(local_end.date):
        rows.append(_row(summary, deterministic, group["mean"].idxmax()))
    return rows


def daily_windows(summary, deterministic):
    """Whichever convention config selects."""
    if config.DAILY_WINDOW_MODE == "peak":
        return peak_daily_windows(summary, deterministic)
    return rain_day_windows(summary, deterministic)
