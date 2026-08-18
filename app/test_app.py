import unittest
from unittest.mock import patch

import app as app_module


class ParseErrorRateTests(unittest.TestCase):
    def test_accepts_closed_unit_interval(self):
        for raw, expected in (("0", 0.0), ("0.25", 0.25), ("1", 1.0)):
            with self.subTest(raw=raw):
                self.assertEqual(app_module.parse_error_rate(raw), expected)

    def test_rejects_invalid_or_non_finite_values(self):
        for raw in ("-0.01", "1.01", "nan", "inf", "not-a-number"):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    app_module.parse_error_rate(raw)


class EndpointTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()

    def test_health_endpoint_is_independent_of_failure_injection(self):
        with patch.object(app_module, "ERR", 1.0):
            response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_error_injection_returns_expected_payload(self):
        with patch.object(app_module, "ERR", 1.0), patch(
            "app.random.random", return_value=0.0
        ):
            response = self.client.get("/")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json()["error"], "injected")


if __name__ == "__main__":
    unittest.main()
