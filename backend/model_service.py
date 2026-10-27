"""QuickML integration and an explicitly labelled, data-trained local fallback."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

import numpy as np
import pandas as pd
import requests
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT = Path(__file__).resolve().parents[1]
TRAINING_FILE = ROOT / "train_telemetry.csv"
FEATURE_COLUMNS = ["timestamp", "ambient_temp_c", "humidity_pct", "solar_irradiance_wm2"]
TARGET_COLUMN = "target_demand_kw"
_model_lock = threading.Lock()
_cached_model: Any | None = None
_cached_evaluation: dict[str, float] | None = None


class ModelIntegrationError(RuntimeError):
    pass


def quickml_endpoint() -> str | None:
    return os.environ.get("QUICKML_ENDPOINT_URL", "").strip() or None


def _features(frame: pd.DataFrame) -> pd.DataFrame:
    timestamps = pd.to_datetime(frame["timestamp"], format="%Y-%m-%d %H:%M:%S", errors="raise")
    hour = timestamps.dt.hour + timestamps.dt.minute / 60
    day = timestamps.dt.day_of_year
    weekday = timestamps.dt.day_of_week
    return pd.DataFrame({
        "ambient_temp_c": pd.to_numeric(frame["ambient_temp_c"]),
        "humidity_pct": pd.to_numeric(frame["humidity_pct"]),
        "solar_irradiance_wm2": pd.to_numeric(frame["solar_irradiance_wm2"]),
        "hour_sin": np.sin(2 * np.pi * hour / 24),
        "hour_cos": np.cos(2 * np.pi * hour / 24),
        "day_sin": np.sin(2 * np.pi * day / 365.25),
        "day_cos": np.cos(2 * np.pi * day / 365.25),
        "weekday_sin": np.sin(2 * np.pi * weekday / 7),
        "weekday_cos": np.cos(2 * np.pi * weekday / 7),
    })


def _load_local_model() -> tuple[Any, dict[str, float]]:
    global _cached_model, _cached_evaluation
    if _cached_model is not None and _cached_evaluation is not None:
        return _cached_model, _cached_evaluation
    with _model_lock:
        if _cached_model is not None and _cached_evaluation is not None:
            return _cached_model, _cached_evaluation
        if not TRAINING_FILE.exists():
            raise ModelIntegrationError(f"Official training data is missing: {TRAINING_FILE.name}.")
        training = pd.read_csv(TRAINING_FILE)
        required = FEATURE_COLUMNS + [TARGET_COLUMN]
        missing = [column for column in required if column not in training.columns]
        if missing:
            raise ModelIntegrationError(f"Training file is missing required columns: {', '.join(missing)}.")
        training = training[required].copy()
        training["timestamp"] = pd.to_datetime(training["timestamp"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
        for column in FEATURE_COLUMNS[1:] + [TARGET_COLUMN]:
            training[column] = pd.to_numeric(training[column], errors="coerce")
        training = training.dropna(subset=required)
        if len(training) < 10:
            raise ModelIntegrationError("Official training data has too few clean rows to fit a local demonstration model.")
        training["timestamp"] = training["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
        training = training.sort_values("timestamp").reset_index(drop=True)

        split = max(1, int(len(training) * 0.8))
        train_x = _features(training.iloc[:split])
        holdout_x = _features(training.iloc[split:])
        y_train = training[TARGET_COLUMN].iloc[:split].to_numpy(dtype=float)
        y_holdout = training[TARGET_COLUMN].iloc[split:].to_numpy(dtype=float)
        # Compare two small tree ensembles on a chronological holdout, then fit the winner on all official rows.
        candidates = [
            ("HistGradientBoosting", HistGradientBoostingRegressor(max_iter=160, learning_rate=0.07, l2_regularization=1.0, random_state=42)),
            ("RandomForest", RandomForestRegressor(n_estimators=160, max_depth=14, min_samples_leaf=3, max_features=0.9, n_jobs=1, random_state=42)),
        ]
        best_model = None
        best_rmse = float("inf")
        best_name = ""
        for name, candidate in candidates:
            candidate.fit(train_x, y_train)
            holdout_predictions = candidate.predict(holdout_x)
            rmse = float(np.sqrt(mean_squared_error(y_holdout, holdout_predictions)))
            if rmse < best_rmse:
                best_model, best_rmse, best_name = candidate, rmse, name
                best_mae = float(mean_absolute_error(y_holdout, holdout_predictions))
        best_model.fit(_features(training), training[TARGET_COLUMN].to_numpy(dtype=float))
        _cached_model = best_model
        _cached_evaluation = {"rmse_kw": round(best_rmse, 3), "mae_kw": round(best_mae, 3), "holdout_rows": len(y_holdout), "training_rows": len(training), "model_name": best_name}
        return _cached_model, _cached_evaluation


def _quickml_predictions(frame: pd.DataFrame, endpoint: str) -> np.ndarray:
    headers = {"Content-Type": "application/json"}
    endpoint_key = os.environ.get("QUICKML_ENDPOINT_KEY", "").strip()
    oauth_token = os.environ.get("ZOHO_OAUTH_TOKEN", "").strip()
    catalyst_org = os.environ.get("CATALYST_ORG", "").strip()
    environment = os.environ.get("CATALYST_ENVIRONMENT", "").strip()
    if endpoint_key:
        headers["X-QUICKML-ENDPOINT-KEY"] = endpoint_key
    if oauth_token:
        headers["Authorization"] = oauth_token if oauth_token.lower().startswith("zoho-oauthtoken ") else f"Zoho-oauthtoken {oauth_token}"
    if catalyst_org:
        headers["CATALYST-ORG"] = catalyst_org
    if environment:
        headers["Environment"] = environment
    try:
        response = requests.post(endpoint, json={"data": frame[FEATURE_COLUMNS].to_dict(orient="records")}, headers=headers, timeout=20)
        if response.status_code == 401 or response.status_code == 403:
            raise ModelIntegrationError("QuickML rejected authentication. Check the endpoint key, OAuth token, organization, and environment settings.")
        if response.status_code == 429:
            raise ModelIntegrationError("QuickML rate limit reached. Please retry later.")
        if not response.ok:
            raise ModelIntegrationError(f"QuickML returned HTTP {response.status_code}.")
        result = response.json()
    except requests.Timeout as error:
        raise ModelIntegrationError("QuickML request timed out after 20 seconds.") from error
    except requests.RequestException as error:
        # Avoid echoing a full request URL or its query parameters into UI errors and logs.
        raise ModelIntegrationError("Could not reach the configured QuickML endpoint. Check network access and endpoint settings.") from error
    except ValueError as error:
        raise ModelIntegrationError("QuickML returned malformed JSON.") from error
    if not isinstance(result, dict):
        raise ModelIntegrationError("QuickML response must be a JSON object.")
    if result.get("status") not in (None, "success"):
        raise ModelIntegrationError("QuickML reported that the inference request was unsuccessful.")

    # Keep compatibility with the starter-kit batch response while also accepting
    # the documented Catalyst SDK response: {"status":"success","result":[{"prediction": ...}]}.
    values = result.get("predictions")
    if not isinstance(values, list):
        values = result.get("result")
        if isinstance(values, list):
            values = [item.get("prediction") if isinstance(item, dict) else item for item in values]
    if not isinstance(values, list):
        raise ModelIntegrationError("QuickML response must contain a predictions array or a result array.")
    try:
        predictions = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as error:
        raise ModelIntegrationError("QuickML returned non-numerical predictions.") from error
    if predictions.ndim != 1 or len(predictions) != len(frame):
        raise ModelIntegrationError(f"QuickML returned {len(predictions)} predictions for {len(frame)} input rows.")
    if not np.isfinite(predictions).all():
        raise ModelIntegrationError("QuickML returned NaN or infinite predictions.")
    return predictions


@dataclass
class PredictionResult:
    predictions: np.ndarray
    model_source: str
    evaluation: dict[str, float] | None = None


def predict_features(frame: pd.DataFrame) -> PredictionResult:
    """Use QuickML when configured; otherwise use an explicitly named local demo model."""
    endpoint = quickml_endpoint()
    if endpoint:
        predictions = _quickml_predictions(frame, endpoint)
        return PredictionResult(predictions, "Zoho Catalyst QuickML", None)
    model, evaluation = _load_local_model()
    predictions = np.asarray(model.predict(_features(frame)), dtype=float)
    if len(predictions) != len(frame) or not np.isfinite(predictions).all():
        raise ModelIntegrationError("Local demonstration model returned invalid predictions.")
    return PredictionResult(predictions, "Local demo model trained on official data (not QuickML)", evaluation)


def model_status() -> dict[str, Any]:
    endpoint = quickml_endpoint()
    return {
        "quickml_configured": bool(endpoint),
        "quickml_status": "Configured; connection is verified on forecast" if endpoint else "Not configured",
        "prediction_source": "Zoho Catalyst QuickML" if endpoint else "Local demonstration model",
        "api_token_configured": bool(os.environ.get("ZOHO_OAUTH_TOKEN", "").strip() or os.environ.get("QUICKML_ENDPOINT_KEY", "").strip()),
        "uncertainty": "Point estimates; prediction uncertainty is not quantified.",
    }
