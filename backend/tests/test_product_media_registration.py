import unittest
from fastapi.testclient import TestClient
from app import main


class ProductMediaRegistrationAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.old_url, self.old_key = main.settings.supabase_url, main.settings.supabase_anon_key
        main.settings.supabase_url = "https://example.supabase.co"
        main.settings.supabase_anon_key = "test-anon-key"

    def tearDown(self):
        main.app.dependency_overrides.clear()
        main.settings.supabase_url, main.settings.supabase_anon_key = self.old_url, self.old_key

    def test_media_registration_requires_authentication(self):
        response = self.client.post(
            "/v1/admin/catalog/products/00000000-0000-4000-8000-000000000001/media",
            json={"storage_path":"00000000-0000-4000-8000-000000000001/image.jpg","alt_text":"Foto komponen uji","content_type":"image/jpeg","byte_size":12,"sha256":"a"*64,"rights_status":"unknown"},
        )
        self.assertEqual(response.status_code, 401)

    def test_customer_role_cannot_register_product_media(self):
        main.app.dependency_overrides[main.get_current_identity] = lambda: {
            "user":{"id":"customer-1"},"profile":{"id":"customer-1","role":"customer","is_active":True},
            "role":"customer","_access_token":"customer-token",
        }
        response = self.client.post(
            "/v1/admin/catalog/products/00000000-0000-4000-8000-000000000001/media",
            json={"storage_path":"00000000-0000-4000-8000-000000000001/image.jpg","alt_text":"Foto komponen uji","content_type":"image/jpeg","byte_size":12,"sha256":"a"*64,"rights_status":"unknown"},
        )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
