"""Small dependency-light HTTP server for local demos and Catalyst AppSail."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from sqlite3 import Error as SQLiteError
from urllib.parse import urlparse

import pandas as pd

from backend.grid_engine import InputValidationError, build_forecast, parse_tabular_text, validate_records
from backend.model_service import ModelIntegrationError, model_status, predict_features
from backend.store import check_store, delete_dataset, get_dataset, get_forecast, initialize_store, list_datasets, list_forecasts, save_dataset, save_forecast

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "frontend"
SAMPLE_FILE = ROOT / "sample_test_input.csv"
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("gridsense")


class GridSenseHandler(BaseHTTPRequestHandler):
    server_version = "GridSenseAI/1.0"

    def log_message(self, format: str, *args: object) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def _send_json(self, status: int, payload: dict) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _read_body(self) -> bytes:
        limit = 2_000_000
        self.connection.settimeout(30)
        transfers = self.headers.get_all("Transfer-Encoding", [])
        lengths = self.headers.get_all("Content-Length", [])

        if transfers:
            if lengths or len(transfers) != 1 or transfers[0].strip().lower() != "chunked":
                raise InputValidationError("Unsupported or ambiguous request framing.")

            body = bytearray()
            for _ in range(10000):
                line = self.rfile.readline(8193)
                if len(line) > 8192 or not line.endswith(b"\r\n"):
                    raise InputValidationError("Invalid chunk header.")

                token = line[:-2].split(b";", 1)[0]
                if not token or any(c not in b"0123456789abcdefABCDEF" for c in token):
                    raise InputValidationError("Invalid chunk size.")

                size = int(token, 16)
                if len(body) + size > limit:
                    raise InputValidationError("Request body exceeds the 2 MB limit.")

                if size == 0:
                    trailer_bytes = 0
                    while True:
                        trailer = self.rfile.readline(8193)
                        trailer_bytes += len(trailer)
                        if trailer_bytes > 8192 or not trailer.endswith(b"\r\n"):
                            raise InputValidationError("Invalid chunk trailers.")
                        if trailer == b"\r\n":
                            return bytes(body)
                        if b":" not in trailer:
                            raise InputValidationError("Invalid chunk trailers.")

                chunk = self.rfile.read(size)
                if len(chunk) != size or self.rfile.read(2) != b"\r\n":
                    raise InputValidationError("Incomplete chunked request body.")
                body.extend(chunk)

            raise InputValidationError("Too many request chunks.")

        if len(lengths) > 1:
            raise InputValidationError("Ambiguous request content length.")

        try:
            length = int(lengths[0]) if lengths else 0
        except ValueError as error:
            raise InputValidationError("Invalid request content length.") from error

        if length <= 0:
            raise InputValidationError("Request body is empty.")
        if length > limit:
            raise InputValidationError("Request body exceeds the 2 MB limit.")

        body = self.rfile.read(length)
        if len(body) != length:
            raise InputValidationError("Incomplete request body.")
        return body

    def _read_json(self) -> dict:
        self.close_connection = True
        try:
            body = self._read_body()
        except (OSError, TimeoutError) as error:
            raise InputValidationError("Request body could not be read completely.") from error

        if not body:
            raise InputValidationError("Request body is empty.")

        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise InputValidationError("Request body must be valid JSON.") from error

        if not isinstance(payload, dict):
            raise InputValidationError("Request body must be a JSON object.")
        return payload

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler interface
        path = urlparse(self.path).path
        if path == "/api/ready":
            try:
                check_store()
                assets = [WEB_ROOT / name for name in ("index.html", "app.js", "styles.css", "intake.css")]
                assets.append(SAMPLE_FILE)
                if not model_status()["quickml_configured"]:
                    assets.append(ROOT / "train_telemetry.csv")
                if not all(asset.is_file() for asset in assets):
                    raise OSError("Required application assets are missing")
            except (SQLiteError, OSError):
                logger.exception("Application readiness check failed")
                self._send_json(503, {"status": "not_ready", "error": "Check database access and packaged application assets. Inspect server logs for details."})
                return
            self._send_json(200, {"status": "ready", "checks": {"database": "ok", "assets": "ok"}, "quickml_inference": "Not checked; verify with a forecast."})
            return
        if path == "/api/health":
            self._send_json(200, {"status": "ok", "service": "GridSense AI", "timestamp": datetime.now(timezone.utc).isoformat(), "model": model_status(), "infrastructure": "Software decision support only; no hardware is connected."})
            return
        if path == "/api/sample":
            if not SAMPLE_FILE.exists():
                self._send_json(503, {"error": "Official sample_test_input.csv is not available."})
                return
            try:
                sample = pd.read_csv(SAMPLE_FILE, dtype={"timestamp": str}).head(24)
                rows = validate_records(sample.to_dict(orient="records"), require_24_hour_window=True)
                self._send_json(200, {"rows": rows, "source": "First 24 rows of official sample_test_input.csv", "row_count": len(rows)})
            except (OSError, pd.errors.ParserError, InputValidationError) as error:
                logger.exception("Could not load official sample input")
                self._send_json(500, {"error": f"Official sample input could not be loaded: {error}"})
            return
        if path == "/api/datasets":
            try:
                self._send_json(200, {"datasets": list_datasets()})
            except SQLiteError:
                logger.exception("Could not list saved data sets")
                self._send_json(503, {"error": "Saved data is temporarily unavailable. Check the database path and permissions."})
            return
        if path.startswith("/api/datasets/"):
            dataset_id = path.removeprefix("/api/datasets/").strip("/")
            if not dataset_id or "/" in dataset_id:
                self._send_json(404, {"error": "Saved data set not found."})
                return
            try:
                dataset = get_dataset(dataset_id)
            except (SQLiteError, json.JSONDecodeError):
                logger.exception("Could not load saved data set")
                self._send_json(503, {"error": "Saved data is temporarily unavailable."})
                return
            if dataset is None:
                self._send_json(404, {"error": "Saved data set not found."})
            else:
                self._send_json(200, dataset)
            return
        if path == "/api/forecasts":
            try:
                self._send_json(200, {"forecasts": list_forecasts()})
            except (SQLiteError, json.JSONDecodeError):
                logger.exception("Could not list saved forecasts")
                self._send_json(503, {"error": "Forecast history is temporarily unavailable."})
            return
        if path.startswith("/api/forecasts/"):
            forecast_id = path.removeprefix("/api/forecasts/").strip("/")
            if not forecast_id or "/" in forecast_id:
                self._send_json(404, {"error": "Saved forecast not found."})
                return
            try:
                forecast = get_forecast(forecast_id)
            except (SQLiteError, json.JSONDecodeError):
                logger.exception("Could not load saved forecast")
                self._send_json(503, {"error": "Forecast history is temporarily unavailable."})
                return
            if forecast is None:
                self._send_json(404, {"error": "Saved forecast not found."})
            else:
                self._send_json(200, forecast)
            return
        if path.startswith("/api/"):
            self._send_json(404, {"error": "API route not found."})
            return
        self._serve_static(path)

    def _serve_static(self, url_path: str) -> None:
        relative = "index.html" if url_path in ("", "/") else url_path.lstrip("/")
        candidate = (WEB_ROOT / relative).resolve()
        if WEB_ROOT.resolve() not in candidate.parents and candidate != WEB_ROOT.resolve():
            self._send_json(403, {"error": "Invalid file path."})
            return
        if candidate.is_dir():
            candidate = candidate / "index.html"
        if not candidate.is_file():
            self._send_json(404, {"error": "Page not found."})
            return
        content = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript", "application/json"):
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler interface
        path = urlparse(self.path).path
        if path not in ("/api/forecast", "/api/validate", "/api/datasets"):
            self._send_json(404, {"error": "API route not found."})
            return
        saved_dataset: dict | None = None
        try:
            payload = self._read_json()
            text_input = None
            data_format = None
            for key, candidate_format in (("csv_text", "csv"), ("tsv_text", "tsv"), ("json_text", "json")):
                if key in payload:
                    text_input, data_format = payload[key], candidate_format
                    break
            if "data_text" in payload:
                text_input, data_format = payload["data_text"], str(payload.get("format", "")).lower()
            if path == "/api/validate":
                if text_input is not None:
                    rows = parse_tabular_text(text_input, data_format or "", require_24_hour_window=True)
                    source = f"Uploaded {data_format.upper()}"
                elif "rows" in payload:
                    rows = validate_records(payload["rows"], require_24_hour_window=True)
                    source = str(payload.get("source", "Manual entry"))[:120]
                else:
                    raise InputValidationError("Choose a CSV, TSV, or JSON file, paste data, or add hourly rows.")
                self._send_json(200, {"accepted_rows": len(rows), "rows": rows, "preview": rows[:5], "message": "All 24 hourly rows are valid.", "input_source": source})
                return

            if path == "/api/datasets":
                rows = validate_records(payload.get("rows", []), require_24_hour_window=True)
                try:
                    saved_dataset = save_dataset(payload.get("name"), payload.get("source", "Manual entry"), rows)
                except ValueError as error:
                    raise InputValidationError(str(error)) from error
                self._send_json(201, saved_dataset)
                return

            dataset_id = str(payload.get("dataset_id", "")).strip()
            if dataset_id:
                saved_dataset = get_dataset(dataset_id)
                if saved_dataset is None:
                    self._send_json(404, {"error": "The selected saved data set no longer exists."})
                    return
                rows = validate_records(saved_dataset["rows"], require_24_hour_window=True)
                dataset_name = saved_dataset["name"]
                input_source = saved_dataset["source"]
            elif text_input is not None:
                rows = parse_tabular_text(text_input, data_format or "", require_24_hour_window=True)
                input_source = f"Uploaded {data_format.upper()}"
                dataset_name = payload.get("dataset_name")
            elif "rows" in payload:
                rows = validate_records(payload["rows"], require_24_hour_window=True)
                input_source = str(payload.get("source", "Manual telemetry"))[:80]
                dataset_name = payload.get("dataset_name")
            else:
                raise InputValidationError("No telemetry rows were provided. Choose an input method and provide a complete 24-hour window.")
            if saved_dataset is None:
                if not dataset_name:
                    dataset_name = f"Forecast input · {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                try:
                    saved_dataset = save_dataset(dataset_name, input_source, rows)
                except ValueError as error:
                    raise InputValidationError(str(error)) from error
            dataset_id = saved_dataset["id"]
            dataset_name = saved_dataset["name"]
            frame = pd.DataFrame(rows)
            prediction_result = predict_features(frame)
            response = build_forecast(rows, prediction_result.predictions, model_source=prediction_result.model_source)
            response["evaluation"] = prediction_result.evaluation
            response["input_source"] = input_source
            response["forecast_id"] = str(uuid.uuid4())
            response["dataset_id"] = dataset_id
            response["dataset_name"] = dataset_name
            response["generated_at"] = datetime.now(timezone.utc).isoformat()
            save_forecast(response, dataset_id=dataset_id, dataset_name=dataset_name, input_source=input_source)
            self._send_json(200, response)
        except InputValidationError as error:
            payload = {"error": str(error), "category": "input_validation"}
            if saved_dataset:
                payload["saved_dataset_id"] = saved_dataset["id"]
            self._send_json(400, payload)
        except ModelIntegrationError as error:
            logger.warning("Forecast could not be generated: %s", error)
            response = {"error": str(error), "category": "model_integration"}
            if saved_dataset:
                response["saved_dataset_id"] = saved_dataset["id"]
            self._send_json(502, response)
        except (ValueError, TypeError) as error:
            response = {"error": str(error), "category": "prediction_validation"}
            if saved_dataset:
                response["saved_dataset_id"] = saved_dataset["id"]
            self._send_json(502, response)
        except SQLiteError:
            logger.exception("Could not save or load GridSense data")
            self._send_json(503, {"error": "GridSense could not access its local data store. Check database path and write permissions.", "category": "storage"})
        except Exception:
            logger.exception("Unexpected forecast failure")
            response = {"error": "Forecast generation failed unexpectedly. Check server logs for details.", "category": "internal_error"}
            if saved_dataset:
                response["saved_dataset_id"] = saved_dataset["id"]
            self._send_json(500, response)

    def do_DELETE(self) -> None:  # noqa: N802 - stdlib handler interface
        path = urlparse(self.path).path
        if not path.startswith("/api/datasets/"):
            self._send_json(404, {"error": "API route not found."})
            return
        dataset_id = path.removeprefix("/api/datasets/").strip("/")
        if not dataset_id or "/" in dataset_id:
            self._send_json(404, {"error": "Saved data set not found."})
            return
        try:
            if not delete_dataset(dataset_id):
                self._send_json(404, {"error": "Saved data set not found."})
            else:
                self._send_json(200, {"deleted": True, "id": dataset_id})
        except SQLiteError:
            logger.exception("Could not delete saved data set")
            self._send_json(503, {"error": "Saved data is temporarily unavailable."})


def main() -> None:
    catalyst_port = os.environ.get("X_ZOHO_CATALYST_LISTEN_PORT", "").strip()
    host = os.environ.get("HOST", "0.0.0.0" if catalyst_port else "127.0.0.1")
    port = int(catalyst_port or os.environ.get("PORT", "5000"))
    initialize_store()
    server = ThreadingHTTPServer((host, port), GridSenseHandler)
    logger.info("GridSense AI listening on http://%s:%s", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
