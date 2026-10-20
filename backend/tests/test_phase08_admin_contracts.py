import unittest
from uuid import UUID

from fastapi.testclient import TestClient
from app import main


class Phase08AdminContractTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.identity = {
            "user": {"id": "00000000-0000-4000-8000-000000000001", "email": "admin@example.invalid"},
            "profile": {
                "id": "00000000-0000-4000-8000-000000000001",
                "role": "admin",
                "is_active": True,
            },
            "role": "admin",
            "_access_token": "caller-jwt",
        }
        self.old_count = main.supabase_count
        self.old_get = main.supabase_get
        self.old_role_rpc = main.supabase_admin_role_rpc
        self.old_user_directory_rpc = main.supabase_admin_user_directory_rpc
        self.old_user_provision_rpc = main.supabase_admin_provision_user_profile_rpc
        main.app.dependency_overrides[main.get_current_identity] = lambda: self.identity
        self.count_calls = []
        async def fake_count(table, params, access_token, select_column="id"):
            self.count_calls.append((table, params, access_token, select_column))
            return 4 if not params else 2
        async def fake_get(table, params, access_token=None):
            self.last_get = (table, params, access_token)
            if table == "products":
                return [{"id": "product-1", "sku": "SKU-1", "name": "Live product", "category": "Part", "condition": "used", "status": "review", "retail_price": None, "updated_at": "2026-10-19T00:00:00Z"}]
            if table == "user_profiles":
                return [{"id": "00000000-0000-4000-8000-000000000002", "display_name": "Operator", "role": "inventory_manager", "is_active": True, "created_at": "2026-10-19T00:00:00Z", "updated_at": "2026-10-19T00:00:00Z"}]
            return [{"id": "audit-1", "actor_user_id": "00000000-0000-4000-8000-000000000001", "action": "admin_set_user_role", "entity_type": "user_profile", "entity_id": "00000000-0000-4000-8000-000000000002", "request_id": "request-0001", "created_at": "2026-10-19T00:00:00Z"}]
        self.fake_count = fake_count
        self.fake_get = fake_get
        main.supabase_count = fake_count
        main.supabase_get = fake_get
        async def fake_user_directory(query, role, status, limit, offset, access_token):
            self.last_user_directory = (query, role, status, limit, offset, access_token)
            if status == "missing_profile":
                items = [{"id": "00000000-0000-4000-8000-000000000003", "display_name": None, "role": None, "is_active": None, "created_at": None, "updated_at": None, "auth_created_at": "2026-10-19T00:00:00Z", "has_profile": False}]
            else:
                items = [{"id": "00000000-0000-4000-8000-000000000002", "display_name": "Operator", "role": "inventory_manager", "is_active": True, "created_at": "2026-10-19T00:00:00Z", "updated_at": "2026-10-19T00:00:00Z", "auth_created_at": "2026-10-19T00:00:00Z", "has_profile": True}]
            return {"items": items, "count": len(items), "limit": limit, "offset": offset, "next_offset": offset + limit if len(items) == limit else None}
        async def fake_user_provision(target_user_id, request_id, access_token):
            self.last_user_provision = (target_user_id, request_id, access_token)
            return {"profile": {"id": str(target_user_id), "role": "customer", "is_active": True, "has_profile": True}, "replayed": False}
        self.fake_user_directory = fake_user_directory
        self.fake_user_provision = fake_user_provision
        main.supabase_admin_user_directory_rpc = fake_user_directory
        main.supabase_admin_provision_user_profile_rpc = fake_user_provision
        async def fake_role_rpc(target_user_id, role, is_active, request_id, access_token):
            self.last_role_rpc = (target_user_id, role, is_active, request_id, access_token)
            return {"profile": {"id": str(target_user_id), "role": role, "is_active": is_active}, "replayed": False}
        self.fake_role_rpc = fake_role_rpc
        main.supabase_admin_role_rpc = fake_role_rpc

    def tearDown(self):
        main.app.dependency_overrides.clear()
        main.supabase_count = self.old_count
        main.supabase_get = self.old_get
        main.supabase_admin_role_rpc = self.old_role_rpc
        main.supabase_admin_user_directory_rpc = self.old_user_directory_rpc
        main.supabase_admin_provision_user_profile_rpc = self.old_user_provision_rpc

    def test_overview_returns_real_api_metrics_and_latest_products(self):
        response = self.client.get("/v1/admin/overview")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["role"], "admin")
        self.assertTrue(body["metrics"]["products"]["available"])
        self.assertEqual(body["metrics"]["products"]["value"], 4)
        self.assertTrue(body["metrics"]["payment_reviews"]["available"])
        self.assertEqual(body["latest_products"][0]["sku"], "SKU-1")
        self.assertTrue(all(call[2] == "caller-jwt" for call in self.count_calls))

    def test_overview_marks_out_of_scope_metrics_unavailable_not_zero(self):
        self.identity["role"] = "inventory_manager"
        self.identity["profile"]["role"] = "inventory_manager"
        self.count_calls.clear()
        response = self.client.get("/v1/admin/overview")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["metrics"]["products"]["available"])
        self.assertIsNone(body["metrics"]["products"]["value"])
        self.assertTrue(body["metrics"]["inventory_movements"]["available"])
        self.assertEqual(body["latest_products"], [])
        self.assertFalse(any(call[0] == "products" for call in self.count_calls))

    def test_users_list_is_paginated_filtered_and_uses_caller_jwt(self):
        response = self.client.get("/v1/admin/users?limit=20&offset=40&q=Operator&role=inventory_manager&status=active")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["role"], "inventory_manager")
        self.assertTrue(response.json()["items"][0]["has_profile"])
        query, role, status, limit, offset, token = self.last_user_directory
        self.assertEqual(query, "Operator")
        self.assertEqual(role, "inventory_manager")
        self.assertEqual(status, "active")
        self.assertEqual(limit, 20)
        self.assertEqual(offset, 40)
        self.assertEqual(token, "caller-jwt")

    def test_users_list_can_filter_auth_identities_missing_profiles(self):
        response = self.client.get("/v1/admin/users?status=missing_profile")
        self.assertEqual(response.status_code, 200)
        item = response.json()["items"][0]
        self.assertFalse(item["has_profile"])
        self.assertIsNone(item["role"])
        self.assertIsNone(item["is_active"])
        self.assertNotIn("email", item)
        self.assertEqual(self.last_user_directory[2], "missing_profile")

    def test_users_list_rejects_unsupported_role_and_status_filters(self):
        bad_role = self.client.get("/v1/admin/users?role=superuser")
        bad_status = self.client.get("/v1/admin/users?status=deleted")
        self.assertEqual(bad_role.status_code, 422)
        self.assertEqual(bad_status.status_code, 422)

    def test_profile_provisioning_requires_idempotency_and_forwards_actor_token(self):
        url = "/v1/admin/users/00000000-0000-4000-8000-000000000003/provision"
        missing_key = self.client.post(url)
        self.assertEqual(missing_key.status_code, 422)
        response = self.client.post(url, headers={"Idempotency-Key": "provision-0001"})
        self.assertEqual(response.status_code, 200)
        target, request_id, token = self.last_user_provision
        self.assertEqual(target, UUID("00000000-0000-4000-8000-000000000003"))
        self.assertEqual(request_id, "provision-0001")
        self.assertEqual(token, "caller-jwt")
        self.assertEqual(response.json()["result"]["profile"]["role"], "customer")

    def test_role_mutation_requires_idempotency_key(self):
        response = self.client.post(
            "/v1/admin/users/00000000-0000-4000-8000-000000000002/role",
            json={"role": "moderator", "is_active": True},
        )
        self.assertEqual(response.status_code, 422)

    def test_role_mutation_validates_role_and_forwards_actor_token(self):
        url = "/v1/admin/users/00000000-0000-4000-8000-000000000002/role"
        invalid = self.client.post(
            url, headers={"Idempotency-Key": "request-0001"},
            json={"role": "superuser", "is_active": True},
        )
        self.assertEqual(invalid.status_code, 422)
        response = self.client.post(
            url, headers={"Idempotency-Key": "request-0002"},
            json={"role": "moderator", "is_active": False},
        )
        self.assertEqual(response.status_code, 200)
        target, role, active, request_id, token = self.last_role_rpc
        self.assertEqual(target, UUID("00000000-0000-4000-8000-000000000002"))
        self.assertEqual(role, "moderator")
        self.assertFalse(active)
        self.assertEqual(request_id, "request-0002")
        self.assertEqual(token, "caller-jwt")

    def test_audit_filters_are_bounded_and_sensitive_details_are_not_selected(self):
        response = self.client.get("/v1/admin/audit?q=role&entity_type=user_profile&limit=25&offset=50")
        self.assertEqual(response.status_code, 200)
        table, params, token = self.last_get
        self.assertEqual(table, "audit_logs")
        self.assertEqual(params["limit"], "25")
        self.assertEqual(params["offset"], "50")
        self.assertNotIn("details", params["select"])
        self.assertEqual(token, "caller-jwt")
        self.assertIn("or", params)

    def test_role_and_audit_controls_are_admin_only(self):
        self.identity["role"] = "catalog_editor"
        self.identity["profile"]["role"] = "catalog_editor"
        users = self.client.get("/v1/admin/users")
        audit = self.client.get("/v1/admin/audit")
        mutation = self.client.post(
            "/v1/admin/users/00000000-0000-4000-8000-000000000002/role",
            headers={"Idempotency-Key": "request-0003"},
            json={"role": "moderator", "is_active": True},
        )
        self.assertEqual(users.status_code, 403)
        self.assertEqual(audit.status_code, 403)
        self.assertEqual(mutation.status_code, 403)


if __name__ == "__main__":
    unittest.main()
