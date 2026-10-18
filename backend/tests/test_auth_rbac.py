import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app import main


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | list | None = None):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


class FakeAsyncClient:
    response = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, *args, **kwargs):
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
        identity = {
            "user": {"id": "user-1"},
            "profile": {"id": "user-1", "role": "admin", "is_active": False},
            "role": "admin",
        }
        with self.assertRaises(HTTPException) as caught:
            await dependency(identity=identity)
        self.assertEqual(caught.exception.status_code, 403)

    async def test_disallowed_role_is_forbidden(self):
        dependency = main.require_roles("admin", "catalog_editor")
        identity = {
            "user": {"id": "user-2"},
            "profile": {"id": "user-2", "role": "customer", "is_active": True},
            "role": "customer",
        }
        with self.assertRaises(HTTPException) as caught:
            await dependency(identity=identity)
        self.assertEqual(caught.exception.status_code, 403)

    async def test_allowed_role_returns_identity(self):
        dependency = main.require_roles("admin", "catalog_editor")
        identity = {
            "user": {"id": "user-3"},
            "profile": {"id": "user-3", "role": "Catalog_Editor", "is_active": True},
            "role": "Catalog_Editor",
        }
        self.assertIs(await dependency(identity=identity), identity)

    def test_empty_role_allowlist_is_rejected(self):
        with self.assertRaises(ValueError):
            main.require_roles(" ", "")


if __name__ == "__main__":
    unittest.main()
