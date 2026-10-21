from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import main


class Phase10PartSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def test_part_number_normalization_ignores_formatting_only(self):
        self.assertEqual(main.normalize_part_number("gtz-7s / 12.0"), "GTZ7S120")
        self.assertEqual(main.normalize_part_number("  A.B_123 "), "AB123")

    def test_exact_part_number_ranks_above_partial_text(self):
        exact = {"part_number": "GTZ 7S", "sku": "OTO-BAT-0001", "name": "Aki motor", "brand": "Brand"}
        partial = {"part_number": "GTZ 7S-X", "sku": "OTO-BAT-0002", "name": "Aki motor", "brand": "Brand"}
        exact_score, exact_reason = main._score_part_search_candidate("GTZ-7S", exact)
        partial_score, _ = main._score_part_search_candidate("GTZ-7S", partial)
        self.assertEqual(exact_score, 100)
        self.assertGreater(exact_score, partial_score)
        self.assertTrue(exact_reason)

    def test_search_returns_only_published_query_results_with_verified_fitment_evidence(self):
        product_id = "00000000-0000-0000-0000-000000000010"
        products = [{
            "id": product_id,
            "sku": "OTO-BAT-0001",
            "slug": "aki-gtz-7s",
            "name": "Aki Motor GTZ 7S",
            "description": "Keterangan katalog",
            "brand": "Example",
            "part_number": "GTZ 7S",
            "condition": "new_aftermarket",
            "condition_grade": None,
            "package_quantity": 1,
            "warranty_days": 30,
            "currency": "IDR",
            "retail_price": 100000,
            "fitment_summary": None,
            "published_at": "2026-10-01T00:00:00Z",
        }]
        fitments = [{
            "product_id": product_id,
            "variant_id": "00000000-0000-0000-0000-000000000011",
            "status": "verified",
            "evidence_url": "https://example.invalid/evidence",
            "evidence_note": "Fixture-only evidence",
            "verified_at": "2026-10-01T00:00:00Z",
            "vehicle_variants": {"id": "00000000-0000-0000-0000-000000000011", "name": "Variant"},
        }]
        with patch.object(main, "supabase_get", new_callable=AsyncMock, side_effect=[[], products, fitments]) as get_rows, patch.object(main, "public_product_media", new_callable=AsyncMock, return_value={}), patch.object(main, "supabase_rpc", new_callable=AsyncMock, return_value=[]):
            response = self.client.get("/v1/search/parts", params={"q": "GTZ-7S", "limit": 5})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["normalized_query"], "GTZ7S")
        self.assertEqual(body["scoring_method"], "deterministic_heuristic_not_probability")
        self.assertEqual(body["items"][0]["match_score"], 100)
        self.assertEqual(body["items"][0]["verified_fitments"][0]["status"], "verified")
        self.assertTrue(any("bukan probabilitas" in note for note in body["items"][0]["uncertainty"]))
        self.assertEqual(get_rows.await_args_list[0].args[0], "part_number_cross_references")
        self.assertEqual(get_rows.await_args_list[0].args[1]["review_status"], "eq.approved")
        self.assertEqual(get_rows.await_args_list[1].args[0], "products")
        self.assertEqual(get_rows.await_args_list[1].args[1]["status"], "eq.published")
        self.assertEqual(get_rows.await_args_list[2].args[0], "product_fitments")
        self.assertEqual(get_rows.await_args_list[2].args[1]["status"], "eq.verified")

    def test_search_rejects_non_alphanumeric_query_after_normalization(self):
        with patch.object(main, "supabase_get", new_callable=AsyncMock) as get_rows:
            response = self.client.get("/v1/search/parts", params={"q": "---"})
        self.assertEqual(response.status_code, 422, response.text)
        get_rows.assert_not_awaited()

    def test_search_excludes_published_row_that_identifies_itself_as_draft(self):
        row = {
            "id": "00000000-0000-0000-0000-000000000012",
            "sku": "OTO-BAT-000008",
            "name": "Aki Motor GTZ7S",
            "part_number": "GTZ7S",
            "condition_grade": "belum diverifikasi",
            "description": "Kandidat draft; tetap draft sampai bukti tersedia.",
        }
        with patch.object(main, "supabase_get", new_callable=AsyncMock, side_effect=[[], [row]]) as get_rows:
            response = self.client.get("/v1/search/parts", params={"q": "GTZ7S"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["items"], [])
        self.assertEqual(get_rows.await_count, 2)


    def test_verified_vehicle_fitment_boosts_candidate_without_changing_fitment_state(self):
        product_id = "00000000-0000-0000-0000-000000000020"
        variant_id = "00000000-0000-0000-0000-000000000021"
        model_id = "00000000-0000-0000-0000-000000000022"
        make_id = "00000000-0000-0000-0000-000000000023"
        product = {"id": product_id, "sku": "OTO-SHK-001", "name": "Shockbreaker motor", "part_number": "SHK-001", "brand": "Example", "condition": "used", "status": "published"}
        fitment = {
            "product_id": product_id, "variant_id": variant_id, "status": "verified",
            "evidence_url": "https://catalog.example/fitment", "verified_at": "2026-10-01T00:00:00Z",
            "vehicle_variants": {
                "id": variant_id, "name": "ABS", "year_start": 2020, "year_end": 2024,
                "vehicle_models": {"id": model_id, "name": "Model X", "vehicle_makes": {"id": make_id, "name": "Make X"}},
            },
        }
        with patch.object(main, "supabase_get", new_callable=AsyncMock, side_effect=[[], [product], [fitment]]) as get_rows, patch.object(main, "public_product_media", new_callable=AsyncMock, return_value={}), patch.object(main, "supabase_rpc", new_callable=AsyncMock, return_value=[]):
            response = self.client.get("/v1/search/parts", params={"q": "shock", "vehicle_variant_id": variant_id, "vehicle_model_id": model_id, "vehicle_make_id": make_id, "vehicle_year": 2022})
        self.assertEqual(response.status_code, 200, response.text)
        item = response.json()["items"][0]
        self.assertEqual(item["vehicle_match_status"], "verified_fitment_match")
        self.assertGreater(item["relevance_score"], item["match_score"])
        self.assertEqual(item["verified_fitments"][0]["status"], "verified")
        self.assertEqual(get_rows.await_args_list[2].args[1]["status"], "eq.verified")

    def test_approved_oem_aftermarket_cross_reference_matches_alternate_number_with_provenance(self):
        product_id = "00000000-0000-0000-0000-000000000030"
        mapping = {
            "id": "00000000-0000-0000-0000-000000000031",
            "canonical_part_number": "OEM-12345", "alternate_part_number": "AF-98765",
            "canonical_normalized": "OEM12345", "alternate_normalized": "AF98765",
            "canonical_type": "oem", "alternate_type": "aftermarket", "relation_type": "cross_reference",
            "source_type": "manufacturer_catalog", "source_name": "Manufacturer catalogue",
            "source_url": "https://manufacturer.example/catalog", "review_status": "approved",
            "reviewed_at": "2026-10-01T00:00:00Z",
        }
        product = {"id": product_id, "sku": "OTO-BRK-1", "name": "Brake part aftermarket", "part_number": "AF-98765", "brand": "Example", "condition": "new_aftermarket", "status": "published"}
        with patch.object(main, "supabase_get", new_callable=AsyncMock, side_effect=[[mapping], [product], []]) as get_rows, patch.object(main, "public_product_media", new_callable=AsyncMock, return_value={}), patch.object(main, "supabase_rpc", new_callable=AsyncMock, return_value=[]):
            response = self.client.get("/v1/search/parts", params={"q": "OEM-12345"})
        self.assertEqual(response.status_code, 200, response.text)
        item = response.json()["items"][0]
        self.assertEqual(item["match_score"], 95)
        self.assertEqual(item["matched_cross_references"][0]["source_url"], "https://manufacturer.example/catalog")
        self.assertTrue(any("cross-reference" in reason for reason in item["match_reasons"]))
        self.assertEqual(get_rows.await_args_list[0].args[1]["review_status"], "eq.approved")

    def test_search_empty_catalog_returns_empty_not_mock_candidates(self):
        with patch.object(main, "supabase_get", new_callable=AsyncMock, side_effect=[[], []]) as get_rows:
            response = self.client.get("/v1/search/parts", params={"q": "shock"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["items"], [])
        self.assertEqual(response.json()["count"], 0)
        self.assertEqual(get_rows.await_count, 2)


if __name__ == "__main__":
    unittest.main()
