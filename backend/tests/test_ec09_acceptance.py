from __future__ import annotations

import hashlib
import hmac
import json
import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import main, payments


class EC09PaymentWebhookAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def test_invalid_payment_signature_is_rejected_before_mutation(self):
        body = json.dumps({
            "event_id": "ec09-invalid-signature", "order_id": "ec09-provider-order-001",
            "payment_id": "ec09-transaction-001", "status": "paid", "amount": 12000,
        }, separators=(",", ":")).encode()
        with patch.object(payments.settings, "rajaongkir_payment_callback_secret", "ec09-ci-secret"), \
             patch.object(payments, "_apply_verified_status", new_callable=AsyncMock) as apply:
            response = self.client.post("/v1/webhooks/rajaongkir", content=body,
                                        headers={"X-Callback-Api-Key": "incorrect"})
        self.assertEqual(response.status_code, 401, response.text)
        apply.assert_not_awaited()

    def test_valid_payment_callback_is_signature_checked_and_amount_parsed(self):
        body = json.dumps({
            "event_id": "ec09-valid-callback-001", "order_id": "ec09-provider-order-001",
            "payment_id": "ec09-transaction-001", "status": "paid", "amount": "12000",
        }, separators=(",", ":")).encode()
        secret = "ec09-ci-secret"
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        with patch.object(payments.settings, "rajaongkir_payment_callback_secret", secret), \
             patch.object(payments, "_apply_verified_status", new_callable=AsyncMock) as apply:
            response = self.client.post("/v1/webhooks/rajaongkir", content=body,
                                        headers={"X-Callback-Api-Key": signature, "X-Request-ID": "ec09-request-001"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["received"])
        apply.assert_awaited_once()
        args = apply.await_args.args
        self.assertEqual(args[0], "provider-event:ec09-valid-callback-001")
        self.assertEqual(args[1:4], ("ec09-provider-order-001", "ec09-transaction-001", "paid"))
        self.assertEqual(args[4], Decimal("12000"))
        self.assertEqual(args[5], hashlib.sha256(body).hexdigest())

    def test_payment_event_id_is_bounded_to_database_key_limit(self):
        body = json.dumps({
            "event_id": "x" * 300, "order_id": "ec09-provider-order-002", "status": "pending",
        }, separators=(",", ":")).encode()
        secret = "ec09-ci-secret"
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        with patch.object(payments.settings, "rajaongkir_payment_callback_secret", secret), \
             patch.object(payments, "_apply_verified_status", new_callable=AsyncMock) as apply:
            response = self.client.post("/v1/webhooks/rajaongkir", content=body,
                                        headers={"X-Callback-Api-Key": signature})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertLessEqual(len(apply.await_args.args[0]), 200)

    def test_paid_callback_requires_amount_and_rejects_unknown_status(self):
        secret = "ec09-ci-secret"
        for payload in (
            {"order_id": "ec09-order-003", "status": "paid"},
            {"order_id": "ec09-order-003", "status": "invented-state", "amount": 1000},
        ):
            body = json.dumps(payload, separators=(",", ":")).encode()
            signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            with patch.object(payments.settings, "rajaongkir_payment_callback_secret", secret), \
                 patch.object(payments, "_apply_verified_status", new_callable=AsyncMock) as apply:
                response = self.client.post("/v1/webhooks/rajaongkir", content=body,
                                            headers={"X-Callback-Api-Key": signature})
            self.assertEqual(response.status_code, 422, response.text)
            apply.assert_not_awaited()

    def test_payment_callback_payload_limit_and_disabled_secret(self):
        with patch.object(payments.settings, "rajaongkir_payment_callback_secret", "ec09-ci-secret"):
            too_large = self.client.post("/v1/webhooks/rajaongkir", content=b"x" * 65537)
        self.assertEqual(too_large.status_code, 413)
        with patch.object(payments.settings, "rajaongkir_payment_callback_secret", ""):
            disabled = self.client.post("/v1/webhooks/rajaongkir", content=b"{}")
        self.assertEqual(disabled.status_code, 503)

    def test_customer_and_admin_payment_routes_require_verified_identity(self):
        order_id = "00000000-0000-0000-0000-000000000009"
        cases = (
            ("GET", "/v1/payments/methods", None),
            ("POST", f"/v1/orders/{order_id}/payment-intent", {"payment_type": "qris", "channel_code": "QRIS"}),
            ("GET", f"/v1/orders/{order_id}/payment-status", None),
            ("POST", "/v1/shipping/quote", {"destination_id": "1", "destination_search": "Bogor", "courier": "jne"}),
            ("POST", "/v1/admin/integrations/reconcile-payments", {"limit": 10}),
        )
        for method, path, payload in cases:
            response = self.client.request(method, path, json=payload)
            self.assertEqual(response.status_code, 401, f"{method} {path}: {response.status_code} {response.text}")

    def test_non_customer_role_cannot_access_payment_methods(self):
        identity = {
            "user": {"id": "00000000-0000-0000-0000-000000000009"},
            "profile": {"id": "00000000-0000-0000-0000-000000000009", "role": "supplier", "is_active": True},
            "role": "supplier", "_access_token": "ci-only-token",
        }
        main.app.dependency_overrides[payments.require_active_profile] = lambda: identity
        try:
            response = self.client.get("/v1/payments/methods")
        finally:
            main.app.dependency_overrides.pop(payments.require_active_profile, None)
        self.assertEqual(response.status_code, 403, response.text)


if __name__ == "__main__":
    unittest.main()
