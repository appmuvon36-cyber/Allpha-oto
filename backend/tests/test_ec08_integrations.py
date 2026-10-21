import unittest

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
        self.assertIsInstance(readiness["providers"]["whatsapp_cloud"]["configured"], bool)
        self.assertNotIn("whatsapp_cloud_api_token", readiness)
        self.assertNotIn("rajaongkir_payment_api_key", readiness)

    def test_consent_contract_rejects_unknown_fields(self):
        with self.assertRaises(Exception):
            WhatsAppConsentRequest.model_validate({"opt_in": True, "consent_version": CONSENT_VERSION, "phone": "6281234567890"})


if __name__ == "__main__":
    unittest.main()
