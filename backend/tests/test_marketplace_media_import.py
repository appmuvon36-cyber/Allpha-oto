import unittest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app import main


class MarketplaceImageImportValidationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_tokopedia_image_cdn_is_allowed(self):
        url = "https://p16-images-common-sign-sg.tokopedia-static.net/path/image.jpeg?sig=test"
        self.assertEqual(main.validate_marketplace_image_url(url), url)

    def test_shopee_image_cdn_is_allowed(self):
        url = "https://down-id.img.susercontent.com/file/abc123"
        self.assertEqual(main.validate_marketplace_image_url(url), url)

    def test_arbitrary_image_host_is_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            main.validate_marketplace_image_url("https://example.com/image.jpg")
        self.assertEqual(caught.exception.status_code, 422)

    def test_non_https_image_is_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            main.validate_marketplace_image_url("http://p16-images-common-sign-sg.tokopedia-static.net/image.jpg")
        self.assertEqual(caught.exception.status_code, 422)

    def test_listing_must_be_from_supported_marketplace(self):
        with self.assertRaises(HTTPException) as caught:
            main.validate_marketplace_image_url("https://example.com/product", listing=True)
        self.assertEqual(caught.exception.status_code, 422)

    def test_image_signature_detection(self):
        self.assertEqual(main.detect_product_image_type(b"\xff\xd8\xff\x00"), "image/jpeg")
        self.assertEqual(main.detect_product_image_type(b"\x89PNG\r\n\x1a\nrest"), "image/png")
        self.assertEqual(main.detect_product_image_type(b"RIFF\x00\x00\x00\x00WEBPrest"), "image/webp")
        self.assertIsNone(main.detect_product_image_type(b"<html>not an image</html>"))

    def test_marketplace_import_requires_authentication(self):
        response = self.client.post(
            "/v1/admin/catalog/products/00000000-0000-4000-8000-000000000001/media/import-marketplace",
            json={
                "image_url": "https://p16-images-common-sign-sg.tokopedia-static.net/image.jpg",
                "source_listing_url": "https://www.tokopedia.com/seller/product",
                "alt_text": "Foto referensi draft komponen",
            },
        )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
