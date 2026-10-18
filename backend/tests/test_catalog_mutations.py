import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app import main

class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code=status_code
        self.payload=payload
    def json(self):
        return self.payload

class FakeAsyncClient:
    response=None
    last_request=None
    def __init__(self,*args,**kwargs): pass
    async def __aenter__(self): return self
    async def __aexit__(self,*args): return False
    async def post(self,*args,**kwargs):
        FakeAsyncClient.last_request=(args,kwargs)
        return self.response
    async def get(self,*args,**kwargs):
        FakeAsyncClient.last_request=(args,kwargs)
        return self.response

class CatalogMutationContractTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(main.app)
        self.old_url,self.old_key=main.settings.supabase_url,main.settings.supabase_anon_key
        main.settings.supabase_url="https://example.supabase.co"
        main.settings.supabase_anon_key="test-anon"
        self.identity={"user":{"id":"staff-1"},"profile":{"id":"staff-1","role":"catalog_editor","is_active":True},"role":"catalog_editor","_access_token":"caller-jwt"}
        main.app.dependency_overrides[main.get_current_identity]=lambda:self.identity
        self.old_rpc=main.supabase_catalog_rpc
    def tearDown(self):
        main.app.dependency_overrides.clear()
        main.settings.supabase_url,main.settings.supabase_anon_key=self.old_url,self.old_key
        main.supabase_catalog_rpc=self.old_rpc
    def test_mutation_requires_idempotency_key(self):
        response=self.client.post("/v1/admin/catalog/mutations",json={"action":"create_product","payload":{"name":"Part"}})
        self.assertEqual(response.status_code,422)
    def test_mutation_rejects_unknown_action(self):
        response=self.client.post("/v1/admin/catalog/mutations",headers={"Idempotency-Key":"request-0001"},json={"action":"drop_database","payload":{}})
        self.assertEqual(response.status_code,422)
    def test_mutation_forwards_caller_jwt_and_request_id(self):
        captured={}
        async def fake_rpc(action,product_id,payload,request_id,access_token):
            captured.update(action=action,product_id=product_id,payload=payload,request_id=request_id,access_token=access_token)
            return {"product":{"id":"product-1","status":"draft"},"replayed":False}
        main.supabase_catalog_rpc=fake_rpc
        response=self.client.post("/v1/admin/catalog/mutations",headers={"Idempotency-Key":"request-0002"},json={"action":"create_product","payload":{"name":"Real item"}})
        self.assertEqual(response.status_code,200)
        self.assertEqual(captured["action"],"create_product")
        self.assertEqual(captured["request_id"],"request-0002")
        self.assertEqual(captured["access_token"],"caller-jwt")
        self.assertEqual(captured["payload"]["name"],"Real item")
    def test_rpc_maps_validation_error_without_leaking_database_detail(self):
        FakeAsyncClient.response=FakeResponse(400,{"code":"22023","message":"publication_requirements_missing"})
        with patch.object(main.httpx,"AsyncClient",FakeAsyncClient):
            with self.assertRaises(Exception) as caught:
                import asyncio
                asyncio.run(main.supabase_catalog_rpc("publish_product",None,{},"request-0003","caller-jwt"))
        self.assertEqual(getattr(caught.exception,"status_code",None),422)
        self.assertNotIn("publication_requirements_missing",str(caught.exception))

if __name__=="__main__":
    unittest.main()
