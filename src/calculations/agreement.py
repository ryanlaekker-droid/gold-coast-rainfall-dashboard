"""
Forecast agreement between independent sources.

Deliberately categorical, not a numeric score. Every classification carries
the reasoning that produced it, so the dashboard can show its working.

A source "indicates an event" when:
  deterministic  its peak 24-hour total reaches the threshold
  ensemble       its mean reaches the threshold, OR at least
                 ENSEMBLE_MEMBER_FRACTION of members do

An ensemble counts as ONE source, not as many members.

Rules:
  strong    two or more sources indicate, windows within 12 hours, and the
            largest amount no more than twice the smallest
  moderate  two or more sources indicate, but timing or magnitude differs
  weak      exactly one source indicates
  none      no source indicates
"""

import config

MAX_TIMING_GAP_HOURS = 12
MAX_MAGNITUDE_RATIO = 2.0
ENSEMBLE_MEMBER_FRACTION = 0.25

GE = "\u2265"          # the >= symbol, written as an escape so the file
                       # stays plain ASCII and cannot be broken by an
                       # editor saving in the wrong encoding


def _local(timestamp):
    return timestamp.tz_convert(config.LOCAL_TZ)


def _describe(entry):
    peak = entry["peak"]
    text = (f"{entry['label']} {peak['value']:.1f} mm to "
            f"{_local(peak['end']):%a %d %H:%M}")
    if entry.get("member_fraction") is not None:
        share = entry["member_fraction"]
        text += f" ({int(round(share * 100))}% of members over threshold)"
    return text


def build_entry(label, peak, member_fraction=None, covers_window=True):
    return {
        "label": label,
        "peak": peak,
        "member_fraction": member_fraction,
        "covers_window": covers_window,
    }


def _indicates(entry):
    if entry["peak"] is None:
        return False
    if entry["peak"]["value"] >= config.THRESHOLD_MM:
        return True
    share = entry.get("member_fraction")
    return share is not None and share >= ENSEMBLE_MEMBER_FRACTION


def _coverage_note(assessed, unassessed):
    total = len(assessed) + len(unassessed)
    if not unassessed:
        return f"All {total} sources cover this window."
    return (f"{len(assessed)} of {total} sources cover this window "
            f"({', '.join(unassessed)} do not).")


def classify(entries):
    assessed = [e for e in entries
                if e["peak"] is not None and e.get("covers_window", True)]
    unassessed = [e["label"] for e in entries
                  if e["peak"] is None or not e.get("covers_window", True)]
    indicating = [e for e in assessed if _indicates(e)]

    limit = f"{GE}{config.THRESHOLD_MM:.0f} mm"
    coverage = _coverage_note([e["label"] for e in assessed], unassessed)

    result = {
        "sources_indicating": [e["label"] for e in indicating],
        "sources_assessed": [e["label"] for e in assessed],
        "sources_unassessed": unassessed,
        "coverage": coverage,
    }

    if not indicating:
        result["level"] = "none"
        result["reasoning"] = (
            f"No source indicates {limit} in any 24-hour window. {coverage}")
        return result

    if len(indicating) == 1:
        result["level"] = "weak"
        result["reasoning"] = (
            f"Only {_describe(indicating[0])} indicates {limit}. "
            f"No other source agrees. {coverage}")
        return result

    ends = [e["peak"]["end"] for e in indicating]
    values = [e["peak"]["value"] for e in indicating]

    gap_hours = (max(ends) - min(ends)).total_seconds() / 3600
    ratio = max(values) / min(values) if min(values) > 0 else float("inf")

    detail = "; ".join(_describe(e) for e in indicating)
    timing_ok = gap_hours <= MAX_TIMING_GAP_HOURS
    magnitude_ok = ratio <= MAX_MAGNITUDE_RATIO

    if timing_ok and magnitude_ok:
        result["level"] = "strong"
        result["reasoning"] = (
            f"{len(indicating)} independent sources indicate {limit} within "
            f"{gap_hours:.0f} hours of each other ({detail}). {coverage}")
        return result

    problems = []
    if not timing_ok:
        problems.append(f"windows differ by {gap_hours:.0f} hours")
    if not magnitude_ok:
        problems.append(f"amounts differ by a factor of {ratio:.1f}")

    result["level"] = "moderate"
    result["reasoning"] = (
        f"{len(indicating)} sources indicate {limit}, but "
        f"{' and '.join(problems)} ({detail}). {coverage}")
    return result


def headline_status(peak_stats, agreement_level):
    mean = peak_stats["mean"]
    p90 = peak_stats["p90"]
    limit = f"{GE}{config.THRESHOLD_MM:.0f} mm"

    if mean >= config.THRESHOLD_MM and agreement_level in ("strong", "moderate"):
        return {"code": "green", "text": f"Potential {limit} event"}

    if p90 >= config.THRESHOLD_MM or mean >= config.THRESHOLD_MM:
        return {"code": "amber",
                "text": f"Possible {limit} event \u2014 uncertain"}

    return {"code": "white",
            "text": f"No significant {limit} event identified"}