from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from backend.model_service import ModelIntegrationError, _quickml_predictions, model_status, predict_features
from predict import predict


class PredictionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sample = pd.read_csv("sample_test_input.csv", dtype={"timestamp": str}).head(24)

    def test_official_input_schema_returns_finite_predictions(self) -> None:
        predictions = predict(self.sample)
        self.assertIsInstance(predictions, np.ndarray)
        self.assertEqual(predictions.shape, (len(self.sample),))
        self.assertTrue(np.isfinite(predictions).all())

    def test_missing_schema_column_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "solar_irradiance_wm2"):
            predict(self.sample.drop(columns=["solar_irradiance_wm2"]))

    def test_endpoint_key_alone_is_reported_as_configured_auth(self) -> None:
        with patch.dict(os.environ, {"QUICKML_ENDPOINT_URL": "https://example.invalid/quickml", "QUICKML_ENDPOINT_KEY": "example-key"}, clear=True):
            status = model_status()
        self.assertTrue(status["quickml_configured"])
        self.assertTrue(status["api_token_configured"])

    def test_demo_mode_reports_no_quickml_auth(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            status = model_status()
        self.assertFalse(status["quickml_configured"])
        self.assertFalse(status["api_token_configured"])

    @patch.dict(os.environ, {"QUICKML_ENDPOINT_URL": "https://example.invalid/quickml", "QUICKML_ENDPOINT_KEY": "example-key", "ZOHO_OAUTH_TOKEN": "example-oauth", "CATALYST_ORG": "example-org", "CATALYST_ENVIRONMENT": "Development"})
    @patch("backend.model_service.requests.post")
    def test_quickml_auth_headers_and_response_are_normalized(self, post: object) -> None:
        class Response:
            status_code = 200
            ok = True

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, list[float]]:
                return {"predictions": [123.4, 124.5]}

        post.return_value = Response()  # type: ignore[attr-defined]
        frame = self.sample.iloc[:2].copy()
        predictions = predict_features(frame)
        self.assertEqual(predictions.model_source, "Zoho Catalyst QuickML")
        self.assertEqual(predictions.predictions.tolist(), [123.4, 124.5])
        headers = post.call_args.kwargs["headers"]  # type: ignore[attr-defined]
        self.assertEqual(headers["X-QUICKML-ENDPOINT-KEY"], "example-key")
        self.assertEqual(headers["Authorization"], "Zoho-oauthtoken example-oauth")
        self.assertEqual(headers["CATALYST-ORG"], "example-org")
        self.assertEqual(headers["Environment"], "Development")

    def test_quickml_failure_does_not_silently_fall_back(self) -> None:
        frame = self.sample.iloc[:2].copy()
        with patch.dict(os.environ, {"QUICKML_ENDPOINT_URL": "https://example.invalid/quickml"}), patch("backend.model_service.requests.post", side_effect=__import__("requests").Timeout("slow")):
            with self.assertRaisesRegex(ModelIntegrationError, "timed out"):
                predict_features(frame)

    def test_connection_error_does_not_echo_endpoint_secrets(self) -> None:
        frame = self.sample.iloc[:2].copy()
        with patch("backend.model_service.requests.post", side_effect=__import__("requests").ConnectionError("https://host.invalid/?token=secret")):
            with self.assertRaisesRegex(ModelIntegrationError, "Could not reach") as raised:
                _quickml_predictions(frame, "https://host.invalid/?token=secret")
        self.assertNotIn("secret", str(raised.exception))

    def test_quickml_malformed_response_rejected(self) -> None:
        frame = self.sample.iloc[:2].copy()

        class Response:
            status_code = 200
            ok = True

            def json(self) -> dict[str, list[float]]:
                return {"values": [10.0, 11.0]}  # Missing official starter contract field.

        with patch("backend.model_service.requests.post", return_value=Response()):
            with self.assertRaisesRegex(ModelIntegrationError, "predictions array"):
                _quickml_predictions(frame, "https://example.invalid")

    def test_quickml_wrong_count_or_nonfinite_value_rejected(self) -> None:
        with self.assertRaisesRegex(ModelIntegrationError, "2 input rows"):
            _quickml_predictions_for_test([120.0])
        with self.assertRaisesRegex(ModelIntegrationError, "NaN or infinite"):
            _quickml_predictions_for_test([float("inf"), 130.0])


def _quickml_predictions_for_test(values: list[float]) -> np.ndarray:
    frame = pd.DataFrame({"timestamp": ["2025-01-01 00:00:00", "2025-01-01 01:00:00"], "ambient_temp_c": [20, 20], "humidity_pct": [50, 50], "solar_irradiance_wm2": [0, 0]})

    class Response:
        status_code = 200
        ok = True

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, list[float]]:
            return {"predictions": values}

    with patch("backend.model_service.requests.post", return_value=Response()):
        return _quickml_predictions(frame, "https://example.invalid")


if __name__ == "__main__":
    unittest.main()
