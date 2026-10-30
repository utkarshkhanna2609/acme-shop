import unittest
from unittest.mock import Mock, patch

import httpx

import app


class PaymentResilienceTests(unittest.TestCase):
    def setUp(self):
        app.payment_failures = 0
        app.payment_circuit_opened_at = None
        app.PAYMENT_FAILURE_THRESHOLD = 5

    def test_timeout_retries_with_idempotency_key(self):
        response = Mock()
        response.raise_for_status.return_value = None
        timeout = httpx.ReadTimeout("provider timed out")
        with patch.object(app.http, "post", side_effect=[timeout, timeout, response]) as post:
            with patch.object(app.time, "sleep") as sleep:
                app._charge_payment(17, 2500)

        self.assertEqual(post.call_count, 3)
        self.assertEqual(post.call_args.kwargs["headers"]["Idempotency-Key"], "17")
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(app.payment_failures, 0)

    def test_timeout_exhaustion_records_transient_failure(self):
        timeout = httpx.ReadTimeout("provider timed out")
        with patch.object(app.http, "post", side_effect=timeout):
            with patch.object(app.time, "sleep"):
                with self.assertRaises(httpx.ReadTimeout):
                    app._charge_payment(17, 2500)

        self.assertEqual(app.payment_failures, 1)

    def test_open_circuit_skips_provider_call(self):
        app.PAYMENT_FAILURE_THRESHOLD = 1
        app._record_payment_transient_failure()
        with patch.object(app.http, "post") as post:
            with self.assertRaises(app.PaymentCircuitOpen):
                app._charge_payment(17, 2500)
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
