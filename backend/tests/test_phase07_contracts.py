import unittest

from fastapi.testclient import TestClient

from app.main import app


class Phase07ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_transaction_routes_are_registered_and_protected(self):
        routes = {(method, path) for path, operations in app.openapi()["paths"].items() for method in operations}
        expected = {
            ("GET", "/v1/cart"),
            ("POST", "/v1/cart/mutations"),
            ("POST", "/v1/checkout"),
            ("GET", "/v1/orders"),
            ("GET", "/v1/orders/{order_id}"),
            ("POST", "/v1/orders/{order_id}/payment-evidence"),
            ("POST", "/v1/orders/{order_id}/cancel"),
            ("POST", "/v1/orders/{order_id}/returns"),
            ("GET", "/v1/admin/inventory"),
            ("GET", "/v1/admin/inventory/ledger"),
            ("POST", "/v1/admin/inventory/mutations"),
            ("POST", "/v1/admin/inventory/expire-reservations"),
            ("GET", "/v1/admin/orders"),
            ("GET", "/v1/admin/payments"),
            ("GET", "/v1/admin/returns"),
            ("POST", "/v1/admin/orders/{order_id}/mutations"),
        }
        self.assertTrue(expected.issubset(routes), f"Missing Phase 07 routes: {expected - routes}")

    def test_checkout_requires_verified_bearer_identity(self):
        response = self.client.post(
            "/v1/checkout",
            json={"items": [{"product_id": "00000000-0000-0000-0000-000000000001", "quantity": 1}],
                  "shipping_address": {"recipient_name": "Test User", "phone": "081234567890", "address": "Jalan Test 123"}},
            headers={"Idempotency-Key": "phase07-checkout-test-001"},
        )
        self.assertEqual(response.status_code, 401)

    def test_inventory_mutation_requires_verified_bearer_identity(self):
        response = self.client.post(
            "/v1/admin/inventory/mutations",
            json={"action": "receipt", "product_id": "00000000-0000-0000-0000-000000000001",
                  "payload": {"quantity": 1, "reason": "contract test"}},
            headers={"Idempotency-Key": "phase07-inventory-test-001"},
        )
        self.assertEqual(response.status_code, 401)

    def test_payment_evidence_requires_verified_bearer_identity(self):
        response = self.client.post(
            "/v1/orders/00000000-0000-0000-0000-000000000001/payment-evidence",
            json={"amount": "1000", "method": "manual_transfer", "evidence_reference": "upload-reference"},
            headers={"Idempotency-Key": "phase07-payment-test-001"},
        )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
