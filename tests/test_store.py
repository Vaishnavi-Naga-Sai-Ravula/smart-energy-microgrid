from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from backend.grid_engine import validate_records
from backend.store import delete_dataset, get_dataset, get_forecast, initialize_store, list_datasets, list_forecasts, save_dataset, save_forecast


def sample_rows() -> list[dict[str, object]]:
    start = datetime(2026, 10, 26)
    rows = [
        {
            "timestamp": (start + timedelta(hours=index)).strftime("%Y-%m-%d %H:%M:%S"),
            "ambient_temp_c": 24.0,
            "humidity_pct": 50.0,
            "solar_irradiance_wm2": 0.0,
        }
        for index in range(24)
    ]
    return validate_records(rows, require_24_hour_window=True)


class PersistentWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.database = Path(self.temp_dir.name) / "gridsense.sqlite3"
        initialize_store(self.database)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_saved_dataset_survives_reinitialization_and_can_be_loaded(self) -> None:
        rows = sample_rows()
        saved = save_dataset("Campus test", "Guided entry", rows, self.database)
        initialize_store(self.database)

        loaded = get_dataset(saved["id"], self.database)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["name"], "Campus test")
        self.assertEqual(loaded["rows"], rows)
        self.assertEqual(list_datasets(self.database)[0]["id"], saved["id"])

    def test_forecast_history_round_trips_and_dataset_delete_is_safe(self) -> None:
        rows = sample_rows()
        dataset = save_dataset("Fictional campus", "JSON import", rows, self.database)
        forecast = {
            "forecast_id": "test-forecast-1",
            "dataset_id": dataset["id"],
            "dataset_name": dataset["name"],
            "input_source": dataset["source"],
            "model_source": "Local demo model",
            "generated_at": "2026-10-26T00:00:00+00:00",
            "summary": {"row_count": 24, "peak_demand_kw": 140.0},
            "results": [],
        }
        save_forecast(forecast, dataset_id=dataset["id"], dataset_name=dataset["name"], input_source=dataset["source"], path=self.database)

        self.assertEqual(get_forecast(forecast["forecast_id"], self.database), forecast)
        self.assertEqual(list_forecasts(self.database)[0]["summary"], forecast["summary"])
        self.assertTrue(delete_dataset(dataset["id"], self.database))
        self.assertIsNone(get_dataset(dataset["id"], self.database))
        self.assertFalse(delete_dataset(dataset["id"], self.database))

    def test_invalid_dataset_name_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "name"):
            save_dataset("", "Manual entry", sample_rows(), self.database)


if __name__ == "__main__":
    unittest.main()
