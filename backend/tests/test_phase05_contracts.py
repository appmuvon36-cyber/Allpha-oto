"""Focused API contract checks for Phase 05 catalog mutations.

These tests validate HTTP/auth dependency contracts only. They do not replace
transactional integration tests against a non-production Supabase fixture.
"""
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

import app.main as api


class Phase05MutationContractTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)
        api.app.dependency_overrides[api.get_current_identity] = lambda: {
            "user": {"id": str(uuid4()), "email": "fixture@example.invalid"},
            "profile": {"role": "catalog_editor", "is_active": True},
            "role": "catalog_editor",
            "_access_token": "test-only-token",
        }

    def tearDown(self):
        api.app.dependency_overrides.clear()

    def test_mutation_requires_authenticated_identity(self):
        api.app.dependency_overrides.clear()
        response = self.client.post(
            "/v1/admin/catalog/mutations",
            json={"action": "create_product", "payload": {"name": "Fixture"}},
            headers={"Idempotency-Key": "test-key-0001"},
        )
        self.assertEqual(response.status_code, 401)

    def test_mutation_requires_idempotency_key(self):
        response = self.client.post(
            "/v1/admin/catalog/mutations",
            json={"action": "create_product", "payload": {"name": "Fixture"}},
        )
        self.assertEqual(response.status_code, 422)

    def test_allowed_mutation_forwards_actor_token_key_and_payload(self):
        fake_result = {"product": {"id": str(uuid4()), "status": "draft"}, "replayed": False}
        with patch.object(api, "supabase_catalog_rpc", new_callable=AsyncMock) as rpc:
            rpc.return_value = fake_result
            response = self.client.post(
                "/v1/admin/catalog/mutations",
                headers={"Idempotency-Key": "phase05-test-key-0001"},
                json={
                    "action": "create_product",
                    "payload": {
                        "sku": "TEST-ONLY",
                        "slug": "test-only",
                        "name": "Fixture product",
                        "category": "fixture",
                        "condition": "new_aftermarket",
                    },
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["result"], fake_result)
        rpc.assert_awaited_once()
        args = rpc.await_args.args
        self.assertEqual(args[0], "create_product")
        self.assertIsNone(args[1])
        self.assertEqual(args[2]["sku"], "TEST-ONLY")
        self.assertEqual(args[3], "phase05-test-key-0001")
        self.assertEqual(args[4], "test-only-token")

    def test_unknown_mutation_is_rejected_before_rpc(self):
        with patch.object(api, "supabase_catalog_rpc", new_callable=AsyncMock) as rpc:
            response = self.client.post(
                "/v1/admin/catalog/mutations",
                headers={"Idempotency-Key": "phase05-test-key-0002"},
                json={"action": "drop_database", "payload": {}},
            )
        self.assertEqual(response.status_code, 422)
        rpc.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
