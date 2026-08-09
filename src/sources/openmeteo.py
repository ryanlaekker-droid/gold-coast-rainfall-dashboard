"""
Fetch rainfall forecasts from Open-Meteo.

Every function returns a result dictionary. Nothing raises: a failed source
returns status "failed" with an error message, so one dead API can never take
down the whole collection run.
"""

from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt

import pandas as pd
import requests

import config


def _now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _distance_km(lat1, lon1, lat2, lon2):
    radius = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (sin(dlat / 2) ** 2
         + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2)
    return 2 * radius * asin(sqrt(a))


def _base_params():
    return {
        "latitude": config.LATITUDE,
        "longitude": config.LONGITUDE,
        "hourly": "precipitation",
        "forecast_days": config.FORECAST_DAYS,
        "past_days": config.PAST_DAYS,
        "timezone": "UTC",
    }


def _grid_point(payload):
    return {
        "latitude": payload["latitude"],
        "longitude": payload["longitude"],
        "elevation_m": payload.get("elevation"),
        "distance_km": round(
            _distance_km(config.LATITUDE, config.LONGITUDE,
                         payload["latitude"], payload["longitude"]), 1),
    }


def _to_frame(payload):
    """Hourly block becomes a table indexed by UTC timestamp."""
    hourly = payload["hourly"]
    index = pd.DatetimeIndex(pd.to_datetime(pd.Series(hourly["time"]), utc=True))
    columns = [key for key in hourly if key != "time"]
    frame = pd.DataFrame({col: hourly[col] for col in columns}, index=index)
    return frame.apply(pd.to_numeric, errors="coerce")


def _failed(label, error):
    return {
        "status": "failed",
        "label": label,
        "error": str(error)[:200],
        "retrieved_at_utc": _now_utc(),
        "frame": None,
    }


def fetch_ensemble():
    """ECMWF IFS 0.25 ensemble. Returns one column per member."""
    model = config.ENSEMBLE_MODEL
    params = {**_base_params(), "models": model["id"]}

    try:
        response = requests.get(config.ENSEMBLE_URL, params=params,
                                timeout=config.REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
        frame = _to_frame(payload)
    except Exception as error:
        return _failed(model["label"], error)

    if frame.empty or frame.isna().all().all():
        return _failed(model["label"], "no usable data returned")

    return {
        "status": "ok",
        "kind": "ensemble",
        "label": model["label"],
        "centre": model["centre"],
        "note": model["note"],
        "model_id": model["id"],
        "member_count": len(frame.columns),
        "grid_point": _grid_point(payload),
        "units": "mm",
        "model_run_utc": None,        # not exposed by this endpoint
        "retrieved_at_utc": _now_utc(),
        "frame": frame,
    }


def fetch_deterministic(model):
    """One deterministic global model. Returns a single column."""
    params = {**_base_params(), "models": model["id"]}

    try:
        response = requests.get(config.FORECAST_URL, params=params,
                                timeout=config.REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
        frame = _to_frame(payload)
    except Exception as error:
        return _failed(model["label"], error)

    if frame.empty or frame.isna().all().all():
        return _failed(model["label"], "no usable data returned")

    series = frame.iloc[:, 0].rename(model["label"])

    return {
        "status": "ok",
        "kind": "deterministic",
        "label": model["label"],
        "centre": model["centre"],
        "model_id": model["id"],
        "grid_point": _grid_point(payload),
        "units": "mm",
        "model_run_utc": None,
        "retrieved_at_utc": _now_utc(),
        "valid_steps": int(series.notna().sum()),
        "frame": series.to_frame(),
    }


def fetch_all_deterministic():
    """Every configured deterministic model, queried separately.

    Separate requests are deliberate: a combined request returns only one
    grid point for all models, which loses per-model provenance.
    """
    return [fetch_deterministic(model) for model in config.DETERMINISTIC_MODELS]
