import unittest
from uuid import UUID

from fastapi.testclient import TestClient
from app import main


class Phase09CustomerCatalogTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.old_get = main.supabase_get\n        self.old_media = main.public_product_media\n\n        async def fake_media(product_ids):\n            return {}\n\n        main.public_product_media = fake_media
        self.calls = []

        async def fake_get(table, params, access_token=None):
            self.calls.append((table, params, access_token))
            if table != "products":
                return []
            if params.get("id") == "eq.00000000-0000-4000-8000-000000000001":
                return [{
                    "id": "00000000-0000-4000-8000-000000000001",
                    "sku": "SKU-REAL-CATALOG-CONTRACT",
                    "name": "Contract product",
                    "status": "published",
                    "condition": "new_oem",
                    "retail_price": "120000",
                    "currency": "IDR",
                }]
            return []

        main.supabase_get = fake_get

    def tearDown(self):
        main.supabase_get = self.old_get\n        main.public_product_media = self.old_media

    def test_public_product_detail_returns_only_published_lookup(self):
        response = self.client.get("/v1/catalog/products/00000000-0000-4000-8000-000000000001")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["product"]["sku"], "SKU-REAL-CATALOG-CONTRACT")
        self.assertEqual(self.calls[0][0], "products")
        self.assertEqual(self.calls[0][1]["status"], "eq.published")
        self.assertEqual(self.calls[0][1]["id"], "eq.00000000-0000-4000-8000-000000000001")

    def test_public_product_detail_hides_missing_or_unpublished_product(self):
        response = self.client.get("/v1/catalog/products/00000000-0000-4000-8000-000000000002")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("draft", response.text.lower())

    def test_public_product_detail_rejects_invalid_uuid(self):
        response = self.client.get("/v1/catalog/products/not-a-uuid")
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
