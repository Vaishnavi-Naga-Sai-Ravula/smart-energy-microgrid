"""Input validation and the official HackSphere transition controller."""

from __future__ import annotations

import csv
import io
import json
import math
import re
from datetime import datetime, timedelta
from typing import Any, Iterable

FEATURE_COLUMNS = (
    "timestamp",
    "ambient_temp_c",
    "humidity_pct",
    "solar_irradiance_wm2",
)
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

_HEADER_ALIASES = {
    "timestamp": {"timestamp", "time_stamp", "datetime", "date_time", "dateandtime"},
    "ambient_temp_c": {"ambient_temp_c", "ambient_temp", "ambient_temperature", "temperature", "temperature_c", "temp", "temp_c", "air_temperature_c", "air_temp_c"},
    "humidity_pct": {"humidity_pct", "humidity_percent", "humidity_percentage", "humidity", "relative_humidity", "relative_humidity_pct", "rh"},
    "solar_irradiance_wm2": {"solar_irradiance_wm2", "solar_irradiance", "solar_radiation_wm2", "solar_radiation", "solar_wm2", "irradiance_wm2", "irradiance", "solar_irradiance_w_m2"},
}
_ALIAS_TO_COLUMN = {alias: column for column, aliases in _HEADER_ALIASES.items() for alias in aliases}
_TIMESTAMP_FORMATS = (
    TIMESTAMP_FORMAT,
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%d-%m-%YT%H:%M:%S",
    "%d-%m-%YT%H:%M",
)


class InputValidationError(ValueError):
    """An input error that is safe to show to an operator."""


def _header_key(value: Any) -> str:
    """Normalize human-written column labels into stable alias lookup keys."""
    text = str(value).strip().lstrip("\ufeff").lower()
    text = text.replace("°", " ").replace("²", "2")
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _parse_timestamp(value: Any) -> datetime:
    text = str(value).strip()
    for date_format in _TIMESTAMP_FORMATS:
        try:
            parsed = datetime.strptime(text, date_format)
            if parsed.strftime(date_format) == text:
                return parsed
        except (TypeError, ValueError):
            continue
    raise ValueError("timestamp must include a date and hour; use YYYY-MM-DD HH:00 or DD-MM-YYYY HH:00.")


def _canonicalize_record(row: dict[str, Any]) -> dict[str, Any]:
    canonical: dict[str, Any] = {}
    date_value: Any = None
    time_value: Any = None
    for raw_key, value in row.items():
        key = _header_key(raw_key)
        column = _ALIAS_TO_COLUMN.get(key)
        if key in {"date", "day"} or key.startswith("date_"):
            date_value = value
        elif key in {"time", "hour", "time_of_day"} or key.startswith("time_") or key.startswith("hour_"):
            time_value = value
        elif column:
            if column in canonical:
                raise InputValidationError(f"Input has more than one column mapped to {column}.")
            canonical[column] = value
    if "timestamp" not in canonical and date_value is not None:
        date_text = str(date_value).strip()
        if time_value is not None:
            time_text = str(time_value).strip()
            if re.fullmatch(r"\d{1,2}", time_text):
                time_text = f"{int(time_text):02d}:00"
            canonical["timestamp"] = f"{date_text} {time_text}"
        else:
            canonical["timestamp"] = date_text
    return canonical


def validate_records(records: Iterable[dict[str, Any]], *, require_24_hour_window: bool = False) -> list[dict[str, Any]]:
    """Validate feature rows, preserving their order and original timestamps."""
    try:
        rows = list(records)
    except TypeError as error:
        raise InputValidationError("Rows must be a list of feature objects.") from error
    if not rows:
        raise InputValidationError("No telemetry rows were provided.")
    if len(rows) > 5000:
        raise InputValidationError("A request can contain at most 5,000 rows.")

    normalized: list[dict[str, Any]] = []
    parsed_times: list[datetime] = []
    issues: list[str] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            issues.append(f"Row {index}: expected an object of feature values.")
            continue
        missing = [column for column in FEATURE_COLUMNS if column not in row or row[column] is None or str(row[column]).strip() == ""]
        if missing:
            issues.append(f"Row {index}: missing {', '.join(missing)}.")
            continue
        try:
            parsed = _parse_timestamp(row["timestamp"])
        except (TypeError, ValueError):
            issues.append(f"Row {index}: timestamp must include a valid date and hourly time, for example 26-10-2026 13:00.")
            continue
        timestamp = parsed.strftime(TIMESTAMP_FORMAT)

        values: dict[str, float] = {}
        ranges = {
            "ambient_temp_c": (-80, 60),
            "humidity_pct": (0, 100),
            "solar_irradiance_wm2": (0, 2000),
        }
        row_invalid = False
        for column, (minimum, maximum) in ranges.items():
            try:
                if isinstance(row[column], bool):
                    raise ValueError
                value = float(row[column])
                if not math.isfinite(value):
                    raise ValueError
            except (TypeError, ValueError, OverflowError):
                issues.append(f"Row {index}: {column} must be a finite number.")
                row_invalid = True
                continue
            if not minimum <= value <= maximum:
                issues.append(f"Row {index}: {column} must be between {minimum} and {maximum}.")
                row_invalid = True
            values[column] = value
        if row_invalid:
            continue
        parsed_times.append(parsed)
        normalized.append({"timestamp": timestamp, **values})

    if issues:
        preview = " ".join(issues[:8])
        suffix = f" Plus {len(issues) - 8} more issue(s)." if len(issues) > 8 else ""
        raise InputValidationError(preview + suffix)

    timestamps = [row["timestamp"] for row in normalized]
    if len(set(timestamps)) != len(timestamps):
        raise InputValidationError("Duplicate timestamps are not allowed in a forecast window.")
    if require_24_hour_window:
        if len(normalized) != 24:
            raise InputValidationError(f"A complete forecast needs exactly 24 hourly rows; received {len(normalized)}.")
        if any(timestamp.minute != 0 or timestamp.second != 0 for timestamp in parsed_times):
            raise InputValidationError("Forecast timestamps must fall on the hour (:00:00).")
        for index, (current, following) in enumerate(zip(parsed_times, parsed_times[1:]), start=1):
            if following - current != timedelta(hours=1):
                raise InputValidationError(f"Rows {index} and {index + 1} must be consecutive forecast hours in ascending order.")
    return normalized


def parse_csv_text(csv_text: str, *, require_24_hour_window: bool = False) -> list[dict[str, Any]]:
    return parse_tabular_text(csv_text, "csv", require_24_hour_window=require_24_hour_window)


def parse_tabular_text(data_text: str, data_format: str, *, require_24_hour_window: bool = False) -> list[dict[str, Any]]:
    """Read CSV, TSV, or JSON rows and map common human-readable headers to model features."""
    if not isinstance(data_text, str) or not data_text.strip():
        raise InputValidationError(f"The {data_format.upper()} input is empty.")
    normalized_format = data_format.strip().lower()
    if normalized_format == "json":
        try:
            payload = json.loads(data_text.lstrip("\ufeff"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise InputValidationError(f"Could not read the JSON: {error.msg if isinstance(error, json.JSONDecodeError) else 'invalid text'}.") from error
        records = payload.get("rows") if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            raise InputValidationError("JSON must be an array of row objects, or an object with a 'rows' array.")
        if not records:
            raise InputValidationError("The JSON contains no data rows.")
        if any(not isinstance(record, dict) for record in records):
            raise InputValidationError("Every JSON row must be an object with named feature values.")
        return validate_records((_canonicalize_record(record) for record in records), require_24_hour_window=require_24_hour_window)
    if normalized_format not in {"csv", "tsv"}:
        raise InputValidationError("Choose a CSV, TSV, or JSON data format.")
    try:
        delimiter = "," if normalized_format == "csv" else "\t"
        reader = csv.DictReader(io.StringIO(data_text.lstrip("\ufeff")), delimiter=delimiter, strict=True)
        headers = reader.fieldnames or []
        if not headers:
            raise InputValidationError(f"The {normalized_format.upper()} needs a header row naming each feature column.")
        normalized_headers = [_header_key(header) for header in headers]
        if len(normalized_headers) != len(set(normalized_headers)):
            raise InputValidationError(f"{normalized_format.upper()} contains duplicate column headers.")
        header_set = set(normalized_headers)
        has_date = "date" in header_set or any(header.startswith("date_") for header in header_set)
        missing = []
        for column in FEATURE_COLUMNS:
            if column == "timestamp":
                if not header_set.intersection(_HEADER_ALIASES[column]) and not has_date:
                    missing.append(column)
            elif not header_set.intersection(_HEADER_ALIASES[column]):
                missing.append(column)
        if missing:
            raise InputValidationError(f"{normalized_format.upper()} is missing required columns: {', '.join(missing)}.")
        rows = list(reader)
    except csv.Error as error:
        raise InputValidationError(f"Could not read the {normalized_format.upper()}: {error}.") from error
    if not rows:
        raise InputValidationError(f"The {normalized_format.upper()} contains headers but no data rows.")
    if any(None in row for row in rows):
        raise InputValidationError(f"The {normalized_format.upper()} has data values without matching column headers.")
    return validate_records((_canonicalize_record(row) for row in rows), require_24_hour_window=require_24_hour_window)


def evaluate_decision(timestamp: str, predicted_demand_kw: float) -> dict[str, Any]:
    demand = float(predicted_demand_kw)
    if not math.isfinite(demand):
        raise ValueError("Predicted demand must be a finite number.")
    hour = datetime.strptime(timestamp, TIMESTAMP_FORMAT).hour
    in_evening_window = 18 <= hour <= 22
    high_demand = demand > 160
    renewable = high_demand or in_evening_window
    reasons = []
    if high_demand:
        reasons.append("forecast demand exceeds 160 kW")
    if in_evening_window:
        reasons.append("timestamp is in the 18:00–22:00 evening window")
    if not reasons:
        reasons.append("demand is at or below 160 kW outside the evening window")
    critical = demand >= 200
    return {
        "power_mode": "Renewable Storage Mode" if renewable else "Main Grid Mode",
        "reason": "; ".join(reasons),
        "critical_overload": critical,
        "alert": "Critical Overload Alert" if critical else None,
    }


def build_forecast(rows: list[dict[str, Any]], predictions: Iterable[float], *, model_source: str) -> dict[str, Any]:
    values = list(predictions)
    if len(values) != len(rows):
        raise ValueError(f"Prediction count mismatch: expected {len(rows)}, got {len(values)}.")
    results = []
    for row, prediction in zip(rows, values):
        demand = float(prediction)
        if not math.isfinite(demand):
            raise ValueError("Model returned a non-finite prediction.")
        decision = evaluate_decision(row["timestamp"], demand)
        # Keep the full model value: rounding near 160/200 kW could disagree with the rule result.
        results.append({**row, "target_demand_kw": demand, **decision})
    if not results:
        raise ValueError("Model returned no forecast rows.")
    peak = max(results, key=lambda item: item["target_demand_kw"])
    main_hours = sum(item["power_mode"] == "Main Grid Mode" for item in results)
    renewable_hours = len(results) - main_hours
    alerts = [item for item in results if item["critical_overload"]]
    avg = sum(item["target_demand_kw"] for item in results) / len(results)
    needs_attention = [item for item in results if item["critical_overload"] or item["target_demand_kw"] > 160]
    return {
        "results": results,
        "summary": {
            "row_count": len(results),
            "peak_demand_kw": peak["target_demand_kw"],
            "peak_timestamp": peak["timestamp"],
            "average_demand_kw": round(avg, 3),
            "main_grid_hours": main_hours,
            "renewable_storage_hours": renewable_hours,
            "critical_alert_count": len(alerts),
            "attention_hours": len(needs_attention),
            "forecast_status": "Critical overload" if alerts else ("Operator attention" if needs_attention else "Within controller thresholds"),
            "uncertainty": "Point estimates; prediction uncertainty is not quantified.",
        },
        "model_source": model_source,
    }
