"""Phase 06 supplier API contracts; all external calls are mocked."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

import app.main as api


class Phase06SupplierContractTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)
        self.user_id = str(uuid4())
        self.identity = {
            "user": {"id": self.user_id, "email": "supplier@example.invalid"},
            "profile": {"role": "customer", "is_active": True},
            "role": "customer",
            "_access_token": "test-only-token",
        }
        api.app.dependency_overrides[api.get_current_identity] = lambda: self.identity

    def tearDown(self):
        api.app.dependency_overrides.clear()

    def test_onboarding_requires_idempotency_key(self):
        response = self.client.post(
            "/v1/supplier/onboarding",
            json={"legal_name": "Fixture Supplier", "display_name": "Fixture"},
        )
        self.assertEqual(response.status_code, 422)

    def test_onboarding_forwards_payload_and_caller_token(self):
        result = {"supplier": {"id": str(uuid4()), "status": "pending_review"}, "replayed": False}
        payload = {
            "legal_name": "Fixture Supplier PT",
            "display_name": "Fixture Parts",
            "supplier_type": "supplier",
            "contact_email": "ops@example.invalid",
            "address": {"city": "Jakarta"},
        }
        with patch.object(api, "supabase_supplier_rpc", new_callable=AsyncMock) as rpc:
            rpc.return_value = result
            response = self.client.post(
                "/v1/supplier/onboarding",
                headers={"Idempotency-Key": "phase06-onboard-0001"},
                json=payload,
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["result"], result)
        rpc.assert_awaited_once()
        args = rpc.await_args.args
        self.assertEqual(args[0], "oto_supplier_onboard")
        self.assertEqual(args[1]["p_payload"]["legal_name"], payload["legal_name"])
        self.assertEqual(args[1]["p_request_id"], "phase06-onboard-0001")
        self.assertEqual(args[2], "test-only-token")

    def test_staff_role_cannot_self_onboard_as_supplier(self):
        self.identity["profile"]["role"] = "catalog_editor"
        self.identity["role"] = "catalog_editor"
        with patch.object(api, "supabase_supplier_rpc", new_callable=AsyncMock) as rpc:
            response = self.client.post(
                "/v1/supplier/onboarding",
                headers={"Idempotency-Key": "phase06-onboard-0002"},
                json={"legal_name": "Fixture Supplier", "display_name": "Fixture"},
            )
        self.assertEqual(response.status_code, 403)
        rpc.assert_not_awaited()

    def test_document_registration_verifies_bytes_and_server_checksum(self):
        supplier_id = str(uuid4())
        path = self.user_id + "/" + supplier_id + "/registration.pdf"
        checksum = "a" * 64
        result = {"document": {"id": str(uuid4()), "status": "pending_review"}, "replayed": False}
        with patch.object(api, "supabase_get", new_callable=AsyncMock) as get_rows:
            get_rows.return_value = [{"id": supplier_id, "status": "pending_review", "owner_user_id": self.user_id}]
            with patch.object(api, "verify_supplier_document_upload", new_callable=AsyncMock) as verify:
                verify.return_value = checksum
                with patch.object(api, "supabase_supplier_rpc", new_callable=AsyncMock) as rpc:
                    rpc.return_value = result
                    response = self.client.post(
                        "/v1/supplier/documents",
                        headers={"Idempotency-Key": "phase06-document-0001"},
                        json={
                            "document_type": "business_registration",
                            "storage_path": path,
                            "original_filename": "registration.pdf",
                            "content_type": "application/pdf",
                            "file_size_bytes": 1024,
                            "sha256": checksum,
                        },
                    )
        self.assertEqual(response.status_code, 200, response.text)
        verify.assert_awaited_once_with(path, "application/pdf", 1024, checksum, "test-only-token")
        args = rpc.await_args.args
        self.assertEqual(args[0], "oto_supplier_document_register")
        self.assertEqual(args[1]["p_payload"]["sha256"], checksum)
        self.assertEqual(args[1]["p_request_id"], "phase06-document-0001")

    def test_document_registration_rejects_path_outside_supplier_folder(self):
        supplier_id = str(uuid4())
        with patch.object(api, "supabase_get", new_callable=AsyncMock) as get_rows:
            get_rows.return_value = [{"id": supplier_id, "status": "pending_review", "owner_user_id": self.user_id}]
            with patch.object(api, "verify_supplier_document_upload", new_callable=AsyncMock) as verify:
                response = self.client.post(
                    "/v1/supplier/documents",
                    headers={"Idempotency-Key": "phase06-document-0002"},
                    json={
                        "document_type": "business_registration",
                        "storage_path": "someone-else/" + supplier_id + "/registration.pdf",
                        "original_filename": "registration.pdf",
                        "content_type": "application/pdf",
                        "file_size_bytes": 1024,
                    },
                )
        self.assertEqual(response.status_code, 422)
        verify.assert_not_awaited()

    def test_supplier_offer_requires_source_evidence(self):
        supplier_id = str(uuid4())
        with patch.object(api, "supabase_get", new_callable=AsyncMock) as get_rows:
            get_rows.return_value = [{"id": supplier_id, "status": "active", "owner_user_id": self.user_id}]
            with patch.object(api, "supabase_supplier_rpc", new_callable=AsyncMock) as rpc:
                response = self.client.post(
                    "/v1/supplier/offers",
                    headers={"Idempotency-Key": "phase06-offer-0001"},
                    json={
                        "supplier_sku": "SP-100",
                        "source_evidence": {},
                        "condition": "new_aftermarket",
                        "unit_cost": "125000",
                        "stock_quantity": 5,
                        "quote_expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                    },
                )
        self.assertEqual(response.status_code, 422)
        rpc.assert_not_awaited()

    def test_supplier_offer_requires_active_owned_supplier(self):
        with patch.object(api, "supabase_get", new_callable=AsyncMock) as get_rows:
            get_rows.return_value = []
            response = self.client.get("/v1/supplier/offers")
        self.assertEqual(response.status_code, 404)

    def test_supplier_offer_forwards_quote_terms_and_token(self):
        supplier_id = str(uuid4())
        result = {"offer": {"id": str(uuid4()), "status": "pending_review"}, "replayed": False}
        payload = {
            "supplier_sku": "SP-100",
            "source_url": "https://supplier.example.invalid/parts/SP-100",
            "source_evidence": {"type": "supplier_quote", "reference": "Q-100"},
            "condition": "new_aftermarket",
            "unit_cost": "125000",
            "asking_price": "149000",
            "stock_quantity": 5,
            "quote_expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            "lead_time_days": 2,
            "minimum_order_quantity": 1,
            "warranty_days": 30,
        }
        with patch.object(api, "supabase_get", new_callable=AsyncMock) as get_rows:
            get_rows.return_value = [{"id": supplier_id, "status": "active", "owner_user_id": self.user_id}]
            with patch.object(api, "supabase_supplier_rpc", new_callable=AsyncMock) as rpc:
                rpc.return_value = result
                response = self.client.post(
                    "/v1/supplier/offers",
                    headers={"Idempotency-Key": "phase06-offer-0002"},
                    json=payload,
                )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["result"], result)
        rpc.assert_awaited_once()
        args = rpc.await_args.args
        self.assertEqual(args[0], "oto_supplier_offer_submit")
        self.assertEqual(args[1]["p_supplier_id"], supplier_id)
        self.assertEqual(args[1]["p_payload"]["lead_time_days"], 2)
        self.assertEqual(args[1]["p_request_id"], "phase06-offer-0002")
        self.assertEqual(args[2], "test-only-token")

    def test_candidate_match_endpoint_forwards_offer_id_and_token(self):
        self.identity["profile"]["role"] = "catalog_editor"
        self.identity["role"] = "catalog_editor"
        offer_id = str(uuid4())
        result = {"offer_id": offer_id, "match_method": "exact_normalized_identifier", "automatic_linking": False, "candidates": []}
        with patch.object(api, "supabase_supplier_rpc", new_callable=AsyncMock) as rpc:
            rpc.return_value = result
            response = self.client.get("/v1/admin/supplier-offers/" + offer_id + "/candidates")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["result"], result)
        rpc.assert_awaited_once_with(
            "oto_supplier_offer_match_candidates",
            {"p_offer_id": offer_id},
            "test-only-token",
        )

    def test_admin_can_request_audited_manual_candidate_link(self):
        self.identity["profile"]["role"] = "inventory_manager"
        self.identity["role"] = "inventory_manager"
        offer_id = str(uuid4())
        product_id = str(uuid4())
        result = {"offer": {"id": offer_id, "product_id": product_id, "status": "pending_review"}, "replayed": False}
        with patch.object(api, "supabase_supplier_rpc", new_callable=AsyncMock) as rpc:
            rpc.return_value = result
            response = self.client.post(
                "/v1/admin/supplier-mutations",
                headers={"Idempotency-Key": "phase06-link-0001"},
                json={"action": "match_offer_product", "offer_id": offer_id, "payload": {"product_id": product_id}},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["result"], result)
        rpc.assert_awaited_once()
        args = rpc.await_args.args
        self.assertEqual(args[0], "oto_supplier_admin_mutate")
        self.assertEqual(args[1]["p_action"], "match_offer_product")
        self.assertEqual(args[1]["p_offer_id"], offer_id)
        self.assertEqual(args[1]["p_payload"]["product_id"], product_id)

    def test_admin_supplier_queue_supports_bounded_pagination(self):
        self.identity["profile"]["role"] = "moderator"
        self.identity["role"] = "moderator"
        with patch.object(api, "supabase_get", new_callable=AsyncMock) as get_rows:
            get_rows.return_value = []
            response = self.client.get("/v1/admin/suppliers?limit=10&offset=20")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["limit"], 10)
        self.assertEqual(response.json()["offset"], 20)
        self.assertIsNone(response.json()["next_offset"])
        args = get_rows.await_args.args
        self.assertEqual(args[1]["limit"], "10")
        self.assertEqual(args[1]["offset"], "20")

    def test_supplier_audit_is_admin_only_paginated_and_excludes_payload(self):
        self.identity["profile"]["role"] = "admin"
        self.identity["role"] = "admin"
        event = {
            "id": str(uuid4()), "actor_user_id": self.user_id, "action": "supplier_offer_submit",
            "entity_type": "supplier_offer", "entity_id": str(uuid4()),
            "request_id": "phase06-offer-0001", "created_at": "2026-10-18T12:00:00+00:00",
        }
        with patch.object(api, "supabase_get", new_callable=AsyncMock) as get_rows:
            get_rows.return_value = [event]
            response = self.client.get("/v1/admin/supplier-audit?limit=10&offset=20")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["items"], [event])
        self.assertEqual(response.json()["limit"], 10)
        self.assertEqual(response.json()["offset"], 20)
        get_rows.assert_awaited_once()
        args = get_rows.await_args.args
        self.assertEqual(args[0], "audit_logs")
        self.assertEqual(args[1]["limit"], "10")
        self.assertEqual(args[1]["offset"], "20")
        self.assertNotIn("details", args[1]["select"])
        self.assertEqual(get_rows.await_args.kwargs["access_token"], "test-only-token")

    def test_admin_supplier_mutation_rejects_unknown_action(self):
        self.identity["profile"]["role"] = "admin"
        self.identity["role"] = "admin"
        with patch.object(api, "supabase_supplier_rpc", new_callable=AsyncMock) as rpc:
            response = self.client.post(
                "/v1/admin/supplier-mutations",
                headers={"Idempotency-Key": "phase06-admin-0001"},
                json={"action": "publish_everything", "payload": {}},
            )
        self.assertEqual(response.status_code, 422)
        rpc.assert_not_awaited()

    def test_supplier_endpoint_requires_bearer_token(self):
        api.app.dependency_overrides.clear()
        response = self.client.get("/v1/supplier/profile")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
