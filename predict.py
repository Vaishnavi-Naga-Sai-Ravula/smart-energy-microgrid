"""HackSphere-compatible prediction entry point.

QuickML is used whenever QUICKML_ENDPOINT_URL is set. With no published endpoint,
the official data-trained local model is used as a clearly labelled demo fallback.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from backend.grid_engine import FEATURE_COLUMNS, validate_records
from backend.model_service import ModelIntegrationError, predict_features


def predict(input_df: pd.DataFrame) -> np.ndarray:
    """Return one finite kW prediction per row, preserving input order.

    Parameters:
        input_df: DataFrame with timestamp and the three official weather features.

    Returns:
        A NumPy array of predictions, compatible with test_eval.py.
    """
    if not isinstance(input_df, pd.DataFrame):
        raise TypeError("predict(input_df) expects a pandas DataFrame.")
    missing = [column for column in FEATURE_COLUMNS if column not in input_df.columns]
    if missing:
        raise ValueError(f"Input is missing required columns: {', '.join(missing)}.")
    feature_columns = list(FEATURE_COLUMNS)
    rows = validate_records(input_df[feature_columns].to_dict(orient="records"))
    frame = pd.DataFrame(rows, columns=feature_columns)
    result = predict_features(frame)
    if len(result.predictions) != len(input_df) or not np.isfinite(result.predictions).all():
        raise ModelIntegrationError("Prediction output did not match the input rows or contained non-finite values.")
    if result.model_source != "Zoho Catalyst QuickML":
        print(f"DEMO FALLBACK: {result.model_source}; this is not a QuickML prediction.", file=sys.stderr)
    return np.asarray(result.predictions, dtype=float)


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict hourly demand using GridSense AI.")
    parser.add_argument("--input", default="sample_test_input.csv", help="CSV with the four official model input columns")
    parser.add_argument("--output", default="predictions.csv", help="Output CSV path")
    args = parser.parse_args()
    source = Path(args.input)
    frame = pd.read_csv(source, dtype={"timestamp": str})
    values = predict(frame)
    output = pd.DataFrame({"timestamp": frame["timestamp"], "target_demand_kw": values})
    output.to_csv(args.output, index=False)
    print(f"Wrote {len(output)} predictions to {args.output}.")
    print(output.head().to_string(index=False))


if __name__ == "__main__":
    main()
