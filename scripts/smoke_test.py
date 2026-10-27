"""Verify a local or deployed GridSense instance using the real forecast workflow.

Creates a labelled sample dataset and forecast in the target workspace.
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def run(base_url: str, require_quickml: bool = False) -> None:
    base = base_url.rstrip("/")
    parsed = urlsplit(base)
    check(parsed.scheme in ("http", "https") and bool(parsed.hostname), "Use the application's HTTP(S) base URL.")
    check(not parsed.username and not parsed.password and not parsed.query and not parsed.fragment, "Use a base URL without credentials, query parameters, or fragments.")
    with requests.Session() as session:
        def request(method: str, path: str, expected: int = 200, **kwargs):
            response = session.request(method, base + path, timeout=(10, 120), **kwargs)
            check(response.status_code == expected, f"{method} {path}: expected HTTP {expected}, got {response.status_code}. Inspect server logs.")
            return response

        for asset in ("/", "/app.js", "/styles.css", "/intake.css"):
            check(bool(request("GET", asset).content), f"Empty application asset: {asset}")
        health = request("GET", "/api/health").json()
        check(health.get("status") == "ok" and health.get("service") == "GridSense AI", "The URL is not a healthy GridSense service.")
        check(request("GET", "/api/ready").json().get("status") == "ready", "Application dependencies are not ready.")
        if require_quickml:
            check(health.get("model", {}).get("quickml_configured"), "QuickML is required but no endpoint is configured.")
        rows = request("GET", "/api/sample").json()["rows"]
        check(len(rows) == 24, "Official sample must contain 24 rows.")
        request("POST", "/api/validate", expected=400, json={"rows": []})
        check(request("POST", "/api/validate", json={"rows": rows}).json().get("accepted_rows") == 24, "Sample validation did not accept all 24 rows.")
        name = "Deployment check " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        dataset = request("POST", "/api/datasets", expected=201, json={"name": name, "source": "Deployment smoke test / official sample", "rows": rows}).json()
        forecast = request("POST", "/api/forecast", json={"dataset_id": dataset["id"]}).json()
        results = forecast["results"]
        check(len(results) == 24, "Forecast must contain 24 predictions.")
        for source, result in zip(rows, results):
            check(source["timestamp"] == result["timestamp"], "Forecast timestamps changed order.")
            check(math.isfinite(float(result["target_demand_kw"])), "Forecast contains a non-finite prediction.")
        if require_quickml:
            check(forecast.get("model_source") == "Zoho Catalyst QuickML", "QuickML was required but the forecast used another source.")
        restored = request("GET", "/api/forecasts/" + forecast["forecast_id"]).json()
        check(restored == forecast, "Persisted forecast differs from the generated result.")
        print("PASS: assets, readiness, validation, 24 finite ordered predictions, and SQLite forecast restoration.")
        print("Prediction source:", forecast["model_source"])
        print("A labelled test dataset and forecast remain in this workspace.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--require-quickml", action="store_true", help="Fail unless real configured QuickML inference succeeds.")
    args = parser.parse_args()
    try:
        run(args.base_url, args.require_quickml)
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        # Do not echo request exception details, which can contain endpoint URLs.
        detail = "Network/TLS request failed; check the target service and network settings." if isinstance(error, requests.RequestException) else str(error)
        print("FAIL:", detail, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
