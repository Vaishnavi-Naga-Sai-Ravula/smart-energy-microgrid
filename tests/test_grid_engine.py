from __future__ import annotations

import unittest

from backend.grid_engine import InputValidationError, build_forecast, evaluate_decision, parse_csv_text, parse_tabular_text, validate_records


def row(timestamp: str, **overrides: object) -> dict[str, object]:
    return {"timestamp": timestamp, "ambient_temp_c": 22.0, "humidity_pct": 50.0, "solar_irradiance_wm2": 0.0, **overrides}


class TransitionBoundaryTests(unittest.TestCase):
    def test_official_boundaries(self) -> None:
        cases = [
            ("2025-01-01 17:00:00", 159.99, "Main Grid Mode", False),
            ("2025-01-01 17:00:00", 160.00, "Main Grid Mode", False),
            ("2025-01-01 17:00:00", 160.01, "Renewable Storage Mode", False),
            ("2025-01-01 18:00:00", 160.00, "Renewable Storage Mode", False),
            ("2025-01-01 22:00:00", 160.00, "Renewable Storage Mode", False),
            ("2025-01-01 23:00:00", 160.00, "Main Grid Mode", False),
            ("2025-01-01 17:00:00", 199.99, "Renewable Storage Mode", False),
            ("2025-01-01 17:00:00", 200.00, "Renewable Storage Mode", True),
            ("2025-01-01 17:00:00", 240.00, "Renewable Storage Mode", True),
            ("2025-01-01 18:00:00", 205.00, "Renewable Storage Mode", True),
        ]
        for timestamp, demand, expected_mode, expected_alert in cases:
            with self.subTest(timestamp=timestamp, demand=demand):
                result = evaluate_decision(timestamp, demand)
                self.assertEqual(result["power_mode"], expected_mode)
                self.assertEqual(result["critical_overload"], expected_alert)
                self.assertEqual(result["alert"] == "Critical Overload Alert", expected_alert)

    def test_reject_nonfinite_demand(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                evaluate_decision("2025-01-01 12:00:00", value)


class IngestionTests(unittest.TestCase):
    def full_window(self) -> list[dict[str, object]]:
        from datetime import datetime, timedelta

        start = datetime(2025, 2, 1, 0, 0)
        return [row((start + timedelta(hours=index)).strftime("%Y-%m-%d %H:%M:%S")) for index in range(24)]

    def test_valid_24_hour_csv(self) -> None:
        rows = self.full_window()
        header = "timestamp,ambient_temp_c,humidity_pct,solar_irradiance_wm2"
        csv_text = header + "\n" + "\n".join(
            f"{item['timestamp']},{item['ambient_temp_c']},{item['humidity_pct']},{item['solar_irradiance_wm2']}" for item in rows
        )
        parsed = parse_csv_text(csv_text, require_24_hour_window=True)
        self.assertEqual(len(parsed), 24)
        self.assertEqual(parsed[0]["timestamp"], rows[0]["timestamp"])
        self.assertEqual(parsed[-1]["timestamp"], rows[-1]["timestamp"])

    def test_tsv_accepts_readable_aliases_and_day_month_year(self) -> None:
        from datetime import datetime, timedelta

        start = datetime(2026, 10, 26, 0, 0)
        header = "Date\tHour\tTemperature (°C)\tHumidity (%)\tSolar Irradiance (W/m²)"
        lines = [header]
        for index in range(24):
            current = start + timedelta(hours=index)
            lines.append(f"{current:%d-%m-%Y}\t{current:%H}\t24.5\t55\t{0 if current.hour < 6 else 400}")
        parsed = parse_tabular_text("\n".join(lines), "tsv", require_24_hour_window=True)
        self.assertEqual(parsed[0]["timestamp"], "2026-10-26 00:00:00")
        self.assertEqual(parsed[-1]["timestamp"], "2026-10-26 23:00:00")
        self.assertEqual(parsed[0]["ambient_temp_c"], 24.5)

    def test_json_array_and_rows_object_are_supported(self) -> None:
        from datetime import datetime, timedelta
        import json

        start = datetime(2026, 10, 26, 0, 0)
        rows = [
            {"date": (start + timedelta(hours=index)).strftime("%d-%m-%Y"), "time": f"{index:02d}:00", "temperature": 24, "humidity": 50, "irradiance": 0}
            for index in range(24)
        ]
        parsed = parse_tabular_text(json.dumps({"rows": rows}), "json", require_24_hour_window=True)
        self.assertEqual(len(parsed), 24)
        self.assertEqual(parsed[23]["timestamp"], "2026-10-26 23:00:00")

    def test_missing_columns_rejected(self) -> None:
        with self.assertRaisesRegex(InputValidationError, "missing required columns"):
            parse_csv_text("timestamp,ambient_temp_c\n2025-02-01 00:00:00,21")

    def test_duplicate_headers_rejected(self) -> None:
        header = "timestamp,ambient_temp_c,humidity_pct,solar_irradiance_wm2,humidity_pct"
        data = "2025-02-01 00:00:00,21,50,0,51"
        with self.assertRaisesRegex(InputValidationError, "duplicate column headers"):
            parse_csv_text(f"{header}\n{data}")

    def test_empty_and_header_only_csv_rejected(self) -> None:
        with self.assertRaisesRegex(InputValidationError, "empty"):
            parse_csv_text("  ")
        with self.assertRaisesRegex(InputValidationError, "no data rows"):
            parse_csv_text("timestamp,ambient_temp_c,humidity_pct,solar_irradiance_wm2\n")

    def test_invalid_timestamp_rejected(self) -> None:
        item = row("2025/02/01 00:00:00")
        with self.assertRaisesRegex(InputValidationError, "valid date and hourly time"):
            validate_records([item])

    def test_missing_and_non_numeric_features_rejected(self) -> None:
        item = row("2025-02-01 00:00:00")
        item["humidity_pct"] = ""
        with self.assertRaisesRegex(InputValidationError, "missing humidity_pct"):
            validate_records([item])
        item["humidity_pct"] = "wet"
        with self.assertRaisesRegex(InputValidationError, "finite number"):
            validate_records([item])

    def test_physical_validation_bounds(self) -> None:
        item = row("2025-02-01 00:00:00", humidity_pct=101)
        with self.assertRaisesRegex(InputValidationError, "between 0 and 100"):
            validate_records([item])
        item = row("2025-02-01 00:00:00", ambient_temp_c=True)
        with self.assertRaisesRegex(InputValidationError, "finite number"):
            validate_records([item])

    def test_duplicate_timestamp_and_order_rejected_for_forecast(self) -> None:
        rows = self.full_window()
        rows[1]["timestamp"] = rows[0]["timestamp"]
        with self.assertRaisesRegex(InputValidationError, "Duplicate timestamps"):
            validate_records(rows, require_24_hour_window=True)
        rows = self.full_window()
        rows[4], rows[5] = rows[5], rows[4]
        with self.assertRaisesRegex(InputValidationError, "consecutive forecast hours"):
            validate_records(rows, require_24_hour_window=True)

    def test_forecast_requires_exactly_24_rows(self) -> None:
        with self.assertRaisesRegex(InputValidationError, "exactly 24"):
            validate_records(self.full_window()[:1], require_24_hour_window=True)

    def test_forecast_requires_top_of_hour_timestamps(self) -> None:
        rows = self.full_window()
        rows[0]["timestamp"] = "2025-02-01 00:30:00"
        rows[1]["timestamp"] = "2025-02-01 01:30:00"
        with self.assertRaisesRegex(InputValidationError, "fall on the hour"):
            validate_records(rows, require_24_hour_window=True)

    def test_prediction_count_and_finite_values_checked(self) -> None:
        rows = validate_records(self.full_window()[:2])
        with self.assertRaisesRegex(ValueError, "count mismatch"):
            build_forecast(rows, [123.0], model_source="test")
        with self.assertRaisesRegex(ValueError, "finite"):
            build_forecast(rows, [123.0, float("nan")], model_source="test")

    def test_forecast_preserves_precision_at_alert_boundary(self) -> None:
        row_199 = validate_records([row("2025-02-01 17:00:00")])[0]
        forecast = build_forecast([row_199], [199.9999], model_source="test")
        result = forecast["results"][0]
        self.assertAlmostEqual(result["target_demand_kw"], 199.9999)
        self.assertFalse(result["critical_overload"])


if __name__ == "__main__":
    unittest.main()
