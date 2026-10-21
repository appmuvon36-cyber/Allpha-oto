import hashlib
import hmac
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app, settings
from app.integrations import CONSENT_VERSION, WhatsAppConsentRequest, _normalize_indonesian_phone, _provider_readiness


class EC08IntegrationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_reliability_routes_are_registered(self):
        routes = {(method.upper(), path) for path, operations in app.openapi()["paths"].items() for method in operations}
        expected = {
            ("GET", "/v1/admin/integrations/status"),
            ("GET", "/v1/admin/integrations/outbox"),
            ("GET", "/v1/admin/integrations/reconciliations"),
            ("POST", "/v1/admin/integrations/outbox/{outbox_id}/retry"),
            ("POST", "/v1/admin/integrations/dispatch"),
            ("POST", "/v1/internal/integrations/dispatch"),
            ("POST", "/v1/admin/integrations/reconcile-payments"),
            ("POST", "/v1/webhooks/whatsapp"),
            ("GET", "/v1/notifications/whatsapp-consent"),
            ("POST", "/v1/notifications/whatsapp-consent"),
            ("POST", "/v1/admin/orders/{order_id}/whatsapp-status-notification"),
        }
        self.assertTrue(expected.issubset(routes), f"Missing EC-08 routes: {expected - routes}")

    def test_admin_and_customer_routes_require_verified_identity(self):
        paths = [
            ("GET", "/v1/admin/integrations/status"),
            ("GET", "/v1/admin/integrations/outbox"),
            ("GET", "/v1/admin/integrations/reconciliations"),
            ("POST", "/v1/admin/integrations/dispatch"),
            ("POST", "/v1/admin/integrations/reconcile-payments"),
            ("GET", "/v1/notifications/whatsapp-consent"),
            ("POST", "/v1/notifications/whatsapp-consent"),
            ("POST", "/v1/admin/orders/00000000-0000-0000-0000-000000000001/whatsapp-status-notification"),
        ]
        for method, path in paths:
            kwargs = {"headers": {"Idempotency-Key": "ec08-contract-test-001"}}
            if method == "POST":
                kwargs["json"] = {"opt_in": True, "consent_version": CONSENT_VERSION}
            response = self.client.request(method, path, **kwargs)
            self.assertEqual(response.status_code, 401, f"{method} {path}: {response.status_code} {response.text}")

    def test_internal_dispatch_requires_configured_secret(self):
        if settings.integration_worker_secret.strip():
            self.skipTest("Worker secret is configured in this runtime; do not test with an unknown secret.")
        response = self.client.post("/v1/internal/integrations/dispatch")
        self.assertEqual(response.status_code, 503)

    def test_indonesian_phone_normalization(self):
        self.assertEqual(_normalize_indonesian_phone("0812-3456-7890"), "6281234567890")
        self.assertEqual(_normalize_indonesian_phone("+62 812 3456 7890"), "6281234567890")
        with self.assertRaises(HTTPException):
            _normalize_indonesian_phone("not-a-phone")

    def test_provider_readiness_exposes_flags_not_credential_names_or_values(self):
        readiness = _provider_readiness()
        self.assertIn("rajaongkir_payment", readiness["providers"])
        self.assertIn("whatsapp_cloud", readiness["providers"])
        self.assertIn("whatsapp_webhook", readiness["providers"])
        self.assertIsInstance(readiness["providers"]["whatsapp_cloud"]["configured"], bool)
        self.assertNotIn("whatsapp_cloud_api_token", readiness)
        self.assertNotIn("rajaongkir_payment_api_key", readiness)

    def test_whatsapp_webhook_verifies_signature_before_processing(self):
        body = b'{"object":"whatsapp_business_account","entry":[]}'
        secret = "ec08-test-app-secret"
        signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        with patch.object(settings, "whatsapp_app_secret", secret):
            rejected = self.client.post("/v1/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": "sha256=bad"})
            self.assertEqual(rejected.status_code, 401)
            accepted = self.client.post("/v1/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": signature})
            self.assertEqual(accepted.status_code, 200, accepted.text)
            self.assertEqual(accepted.json()["accepted"], 0)

    def test_whatsapp_webhook_handshake_uses_constant_time_token_check(self):
        with patch.object(settings, "whatsapp_webhook_verify_token", "ec08-verify-token"):
            accepted = self.client.get("/v1/webhooks/whatsapp", params={
                "hub.mode": "subscribe", "hub.verify_token": "ec08-verify-token", "hub.challenge": "challenge-001"
            })
            rejected = self.client.get("/v1/webhooks/whatsapp", params={
                "hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "challenge-001"
            })
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.text, "challenge-001")
        self.assertEqual(rejected.status_code, 403)

    def test_consent_contract_rejects_unknown_fields(self):
        with self.assertRaises(Exception):
            WhatsAppConsentRequest.model_validate({"opt_in": True, "consent_version": CONSENT_VERSION, "phone": "6281234567890"})


if __name__ == "__main__":
    unittest.main()
