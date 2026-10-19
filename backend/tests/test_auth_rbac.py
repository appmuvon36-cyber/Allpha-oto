import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from app import main


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | list | None = None):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


class FakeAsyncClient:
    response = None
    last_request = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, *args, **kwargs):
        FakeAsyncClient.last_request = (args, kwargs)
        return self.response


class AuthDependencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_bearer_token_returns_401(self):
        with self.assertRaises(HTTPException) as caught:
            await main.get_current_identity(None)
        self.assertEqual(caught.exception.status_code, 401)

    async def test_invalid_token_returns_401(self):
        original_url, original_key = main.settings.supabase_url, main.settings.supabase_anon_key
        main.settings.supabase_url = "https://example.supabase.co"
        main.settings.supabase_anon_key = "test-anon-key"
        FakeAsyncClient.response = FakeResponse(401, {"message": "invalid token"})
        try:
            with patch.object(main.httpx, "AsyncClient", FakeAsyncClient):
                credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid")
                with self.assertRaises(HTTPException) as caught:
                    await main.get_current_identity(credentials)
            self.assertEqual(caught.exception.status_code, 401)
        finally:
            main.settings.supabase_url, main.settings.supabase_anon_key = original_url, original_key

    async def test_inactive_profile_is_forbidden(self):
        dependency = main.require_roles("admin")
        identity = {"user": {"id": "user-1"}, "profile": {"id": "user-1", "role": "admin", "is_active": False}, "role": "admin"}
        with self.assertRaises(HTTPException) as caught:
            await dependency(identity=identity)
        self.assertEqual(caught.exception.status_code, 403)

    async def test_disallowed_role_is_forbidden(self):
        dependency = main.require_roles("admin", "catalog_editor")
        identity = {"user": {"id": "user-2"}, "profile": {"id": "user-2", "role": "customer", "is_active": True}, "role": "customer"}
        with self.assertRaises(HTTPException) as caught:
            await dependency(identity=identity)
        self.assertEqual(caught.exception.status_code, 403)

    async def test_allowed_role_returns_identity(self):
        dependency = main.require_roles("admin", "catalog_editor")
        identity = {"user": {"id": "user-3"}, "profile": {"id": "user-3", "role": "Catalog_Editor", "is_active": True}, "role": "Catalog_Editor"}
        self.assertIs(await dependency(identity=identity), identity)

    def test_empty_role_allowlist_is_rejected(self):
        with self.assertRaises(ValueError):
            main.require_roles(" ", "")


class ApiFeatureTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.original_supabase_get = main.supabase_get\n        self.original_public_product_media = main.public_product_media\n\n        async def fake_media(product_ids):\n            return {}\n\n        main.public_product_media = fake_media

    def tearDown(self):
        main.app.dependency_overrides.clear()
        main.supabase_get = self.original_supabase_get\n        main.public_product_media = self.original_public_product_media

    def test_public_catalog_is_limited_to_published_rows(self):
        captured = {}

        async def fake_get(table, params, access_token=None):
            captured.update(table=table, params=params, access_token=access_token)
            return [{"id": "real-row-placeholder"}]

        main.supabase_get = fake_get
        response = self.client.get("/v1/catalog/products?q=brake&condition=used&limit=10")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(captured["table"], "products")
        self.assertEqual(captured["params"]["status"], "eq.published")
        self.assertEqual(captured["params"]["condition"], "eq.used")
        self.assertEqual(captured["params"]["limit"], "10")

    def test_invalid_condition_is_rejected_before_database_call(self):
        response = self.client.get("/v1/catalog/products?condition=unknown")
        self.assertEqual(response.status_code, 422)

    def test_vehicle_type_filter_is_validated(self):
        response = self.client.get("/v1/vehicles/models?vehicle_type=spaceship")
        self.assertEqual(response.status_code, 422)


class ProtectedCatalogEndpointTests(unittest.TestCase):
    def setUp(self):
        self.original_url, self.original_key = main.settings.supabase_url, main.settings.supabase_anon_key
        main.settings.supabase_url = "https://example.supabase.co"
        main.settings.supabase_anon_key = "test-anon-key"
        self.client = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()
        main.settings.supabase_url, main.settings.supabase_anon_key = self.original_url, self.original_key

    def test_customer_role_is_denied_by_real_catalog_route(self):
        main.app.dependency_overrides[main.get_current_identity] = lambda: {
            "user": {"id": "customer-1"}, "profile": {"id": "customer-1", "role": "customer", "is_active": True},
            "role": "customer", "_access_token": "customer-token",
        }
        response = self.client.get("/v1/admin/products")
        self.assertEqual(response.status_code, 403)

    def test_catalog_editor_can_read_real_catalog_route_without_token_leak(self):
        rows = [{"id": "product-1", "sku": "SKU-1", "name": "Existing product", "status": "draft"}]
        main.app.dependency_overrides[main.get_current_identity] = lambda: {
            "user": {"id": "staff-1"}, "profile": {"id": "staff-1", "role": "catalog_editor", "is_active": True},
            "role": "catalog_editor", "_access_token": "staff-session-token",
        }
        FakeAsyncClient.response = FakeResponse(200, rows)
        with patch.object(main.httpx, "AsyncClient", FakeAsyncClient):
            response = self.client.get("/v1/admin/products")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": rows, "count": 1, "limit": 100})
        self.assertEqual(FakeAsyncClient.last_request[1]["headers"]["Authorization"], "Bearer staff-session-token")
        me_response = self.client.get("/v1/auth/me")
        self.assertNotIn("_access_token", me_response.json())


if __name__ == "__main__":
    unittest.main()
