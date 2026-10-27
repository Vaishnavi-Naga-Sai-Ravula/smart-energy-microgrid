from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.server import GridSenseHandler
from backend.store import initialize_store


class ServerApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.database = Path(self.temp_dir.name) / "server-test.sqlite3"
        initialize_store(self.database)
        self.environment = patch.dict(os.environ, {"GRIDSENSE_DB_PATH": str(self.database)})
        self.environment.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), GridSenseHandler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=3)
        self.environment.stop()
        self.temp_dir.cleanup()

    def request_json(self, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
        connection = HTTPConnection(self.host, self.port, timeout=5)
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        result = json.loads(response.read().decode("utf-8"))
        connection.close()
        return response.status, result

    @staticmethod
    def rows() -> list[dict[str, object]]:
        start = datetime(2026, 10, 26)
        return [
            {
                "timestamp": (start + timedelta(hours=index)).strftime("%Y-%m-%d %H:%M:%S"),
                "ambient_temp_c": 24.0,
                "humidity_pct": 50.0,
                "solar_irradiance_wm2": 0.0,
            }
            for index in range(24)
        ]

    def test_empty_input_returns_actionable_validation_error(self) -> None:
        status, payload = self.request_json("POST", "/api/validate", {})
        self.assertEqual(status, 400)
        self.assertIn("Choose a CSV, TSV, or JSON", payload["error"])

    def test_malformed_rows_return_input_error_not_server_error(self) -> None:
        status, payload = self.request_json("POST", "/api/validate", {"rows": None})
        self.assertEqual(status, 400)
        self.assertIn("Rows must be a list", payload["error"])

    def test_dataset_and_forecast_endpoints_persist_and_restore_results(self) -> None:
        status, dataset = self.request_json("POST", "/api/datasets", {"name": "Fictional site", "source": "Guided entry", "rows": self.rows()})
        self.assertEqual(status, 201)
        status, loaded = self.request_json("GET", f"/api/datasets/{dataset['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(len(loaded["rows"]), 24)

        fake_model = SimpleNamespace(predictions=[150.0] * 24, model_source="Test model", evaluation=None)
        with patch("backend.server.predict_features", return_value=fake_model):
            status, forecast = self.request_json("POST", "/api/forecast", {"dataset_id": dataset["id"]})
        self.assertEqual(status, 200)
        self.assertEqual(forecast["dataset_id"], dataset["id"])
        status, restored = self.request_json("GET", f"/api/forecasts/{forecast['forecast_id']}")
        self.assertEqual(status, 200)
        self.assertEqual(len(restored["results"]), 24)
        status, history = self.request_json("GET", "/api/forecasts")
        self.assertEqual(status, 200)
        self.assertEqual(history["forecasts"][0]["dataset_name"], "Fictional site")

    def test_missing_saved_dataset_is_not_forecast(self) -> None:
        status, payload = self.request_json("POST", "/api/forecast", {"dataset_id": "missing"})
        self.assertEqual(status, 404)
        self.assertIn("no longer exists", payload["error"])


if __name__ == "__main__":
    unittest.main()
