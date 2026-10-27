"""Reproducibly inspect the supplied HackSphere CSVs without changing them."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ["timestamp", "ambient_temp_c", "humidity_pct", "solar_irradiance_wm2"]


def inspect(path: Path) -> None:
    frame = pd.read_csv(path, dtype={"timestamp": "string"})
    print(f"\n{path.name}")
    print(f"  shape: {frame.shape}")
    print(f"  columns: {list(frame.columns)}")
    print(f"  dtypes: {frame.dtypes.astype(str).to_dict()}")
    print(f"  missing: {frame.isna().sum().to_dict()}")
    print(f"  duplicate rows: {int(frame.duplicated().sum())}")
    if "timestamp" in frame:
        parsed = pd.to_datetime(frame["timestamp"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
        ordered = parsed.dropna().sort_values()
        print(f"  invalid timestamps: {int(parsed.isna().sum())}")
        print(f"  unique timestamps: {int(parsed.nunique())}")
        print(f"  timestamp range: {parsed.min()} .. {parsed.max()}")
        print(f"  timestamp ordered: {bool(parsed.is_monotonic_increasing)}")
        print(f"  hourly gaps: {int((ordered.diff().dropna() != pd.Timedelta(hours=1)).sum())}")
    for column in frame.columns:
        if column == "timestamp":
            continue
        values = pd.to_numeric(frame[column], errors="coerce")
        print(f"  {column}: nonnumeric={int(values.isna().sum())}, nonfinite={int((~values.map(lambda value: pd.notna(value) and abs(value) != float('inf'))).sum())}")
        if values.notna().any():
            summary = values.describe(percentiles=[0.25, 0.5, 0.75]).round(3).to_dict()
            print(f"    distribution: {summary}")


if __name__ == "__main__":
    for filename in ("train_telemetry.csv", "sample_test_input.csv"):
        inspect(ROOT / filename)
