"""EC-01 public stock and sourcing request contract tests.
These tests mock network/DB boundaries and do not create real customer requests.
"""
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

import app.main as api


class EC01SourcingStockContracts(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)
        self.user_id = str(uuid4())
        api.app.dependency_overrides[api.get_current_identity] = lambda: {
            "user": {"id": self.user_id, "email": "customer@example.invalid"},
            "profile": {"role": "customer", "is_active": True},
            "role": "customer",
            "_access_token": "test-only-customer-token",
        }

    def tearDown(self):
        api.app.dependency_overrides.clear()

    def test_category_id_includes_descendant_category_names(self):
        root_id, child_id = str(uuid4()), str(uuid4())
        product_id = str(uuid4())
        category_rows = [
            {"id": root_id, "parent_id": None, "name": "Rem"},
            {"id": child_id, "parent_id": root_id, "name": "Rem Depan"},
        ]
        product_rows = [{
            "id": product_id, "sku": "OTC-TEST", "name": "Kampas rem",
            "brand": "Test", "part_number": "OEM-TEST", "category": "Rem Depan",
            "condition": "new_oem", "retail_price": None, "published_at": None,
        }]

        async def fake_get(table, params, access_token=None):
            if table == "product_categories":
                return category_rows
            if table == "products":
                self.assertIn("or", params)
                self.assertIn("Rem", params["or"])
                self.assertIn("Rem Depan", params["or"])
                return product_rows
            raise AssertionError(f"Unexpected table {table}")

        with patch.object(api, "supabase_get", new_callable=AsyncMock, side_effect=fake_get), \
             patch.object(api, "public_product_media", new_callable=AsyncMock, return_value={}), \
             patch.object(api, "supabase_rpc", new_callable=AsyncMock, return_value=[{
                 "product_id": product_id, "stock_status": "low_stock", "checked_at": "2026-10-19T00:00:00Z"
             }]):
            response = self.client.get("/v1/catalog/products", params={"category_id": root_id})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["items"][0]["stock_status"], "low_stock")
        self.assertEqual(response.json()["items"][0]["stock_checked_at"], "2026-10-19T00:00:00Z")

    def test_public_category_endpoint_uses_restricted_rpc(self):
        category_id = str(uuid4())
        rows = [{
            "id": category_id, "parent_id": None, "name": "Rem", "slug": "rem",
            "code": "REM", "description": None, "vehicle_scope": "all",
            "sort_order": 10, "is_active": True,
        }]
        with patch.object(api, "supabase_rpc", new_callable=AsyncMock, return_value=rows) as rpc:
            response = self.client.get("/v1/catalog/categories")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["items"][0]["id"], category_id)
        rpc.assert_awaited_once_with("oto_public_product_categories", {})

    def test_missing_stock_rpc_result_is_never_claimed_available(self):
        product_id = str(uuid4())

        async def fake_get(table, params, access_token=None):
            if table == "products":
                return [{
                    "id": product_id, "sku": "OTC-TEST", "name": "Part", "brand": None,
                    "part_number": None, "category": "Rem", "condition": "used",
                    "retail_price": None, "published_at": None,
                }]
            raise AssertionError(f"Unexpected table {table}")

        with patch.object(api, "supabase_get", new_callable=AsyncMock, side_effect=fake_get), \
             patch.object(api, "public_product_media", new_callable=AsyncMock, return_value={}), \
             patch.object(api, "supabase_rpc", new_callable=AsyncMock, return_value=[]):
            response = self.client.get("/v1/catalog/products")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["items"][0]["stock_status"], "unverified")
        self.assertIsNone(response.json()["items"][0]["stock_checked_at"])

    def test_sourcing_requires_idempotency_key(self):
        response = self.client.post("/v1/sourcing/requests", json={"part_name": "Kampas rem"})
        self.assertEqual(response.status_code, 422)

    def test_sourcing_persists_under_verified_customer_identity(self):
        request_id = str(uuid4())
        saved = {
            "id": request_id, "customer_user_id": self.user_id, "idempotency_key": "ec01-test-key-0001",
            "part_name": "Kampas rem depan", "part_number": "OEM-123", "vehicle_make": "Toyota",
            "vehicle_model": "Avanza", "vehicle_year": 2021, "quantity": 2, "details": "Contoh contract test",
            "status": "requested", "created_at": "2026-10-19T00:00:00Z",
        }
        with patch.object(api, "supabase_write", new_callable=AsyncMock, return_value=[saved]) as write:
            response = self.client.post(
                "/v1/sourcing/requests",
                headers={"Idempotency-Key": "ec01-test-key-0001"},
                json={"part_name": "Kampas rem depan", "part_number": "OEM-123", "vehicle_make": "Toyota",
                      "vehicle_model": "Avanza", "vehicle_year": 2021, "quantity": 2, "details": "Contoh contract test"},
            )

        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["request"]["id"], request_id)
        self.assertEqual(response.json()["request"]["status"], "requested")
        write.assert_awaited_once()
        args = write.await_args.args
        self.assertEqual(args[0], "POST")
        self.assertEqual(args[1], "sourcing_requests")
        self.assertEqual(args[2], "test-only-customer-token")
        self.assertEqual(args[3]["customer_user_id"], self.user_id)
        self.assertEqual(args[3]["status"], "requested")

    def test_non_customer_role_cannot_create_sourcing_request(self):
        api.app.dependency_overrides[api.get_current_identity] = lambda: {
            "user": {"id": self.user_id, "email": "staff@example.invalid"},
            "profile": {"role": "catalog_editor", "is_active": True},
            "role": "catalog_editor",
            "_access_token": "test-only-staff-token",
        }
        response = self.client.post(
            "/v1/sourcing/requests",
            headers={"Idempotency-Key": "ec01-test-key-0002"},
            json={"part_name": "Kampas rem"},
        )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
