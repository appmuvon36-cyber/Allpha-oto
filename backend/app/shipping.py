from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.main import require_active_profile, require_roles, require_supabase_configuration, settings, supabase_get

router = APIRouter()

class ShippingQuoteRequest(BaseModel):
    destination_id: str = Field(min_length=1, max_length=32)
    destination_search: str = Field(min_length=3, max_length=100)
    courier: str | None = Field(default=None, min_length=2, max_length=200)

    model_config = {"extra": "forbid"}

async def rajaongkir_request(method: str, path: str, *, params: dict[str, str] | None = None, data: dict[str, str] | None = None) -> dict[str, Any]:
    api_key = settings.rajaongkir_api_key.strip()
    base_url = settings.rajaongkir_base_url.rstrip("/")
    if not api_key:
        raise HTTPException(status_code=503, detail="Layanan ongkir belum dikonfigurasi.")
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.request(method, base_url + "/" + path.lstrip("/"), headers={"key": api_key, "Accept": "application/json"}, params=params, data=data)
        if response.status_code in (401, 403) or response.status_code == 429 or response.status_code >= 500:
            raise HTTPException(status_code=503, detail="Layanan ongkir sedang tidak tersedia atau kredensial perlu diperiksa.")
        if response.status_code != 200:
            raise HTTPException(status_code=422, detail="Lokasi atau layanan kurir tidak dapat diproses.")
        body = response.json()
        meta = body.get("meta") or {}
        if str(meta.get("status", "")).lower() not in {"success", "true"} and meta.get("code") not in (200, "200"):
            raise HTTPException(status_code=422, detail="RajaOngkir tidak menemukan lokasi atau tarif yang sesuai.")
        return body
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Tidak dapat terhubung ke layanan ongkir.") from exc

async def resolve_origin() -> tuple[str, dict[str, Any]]:
    # Always resolve the warehouse against the live provider directory, even if
    # an operator has filled ORIGIN_ID. A configured ID is a pin, not proof.
    body = await rajaongkir_request("GET", "destination/domestic-destination", params={"search": settings.rajaongkir_origin_search.strip() or "Sasak Panjang", "limit": "50", "offset": "0"})
    matches = [
        row for row in (body.get("data") or [])
        if str(row.get("subdistrict_name", "")).strip().casefold() == "sasak panjang"
        and str(row.get("district_name", "")).strip().casefold() == "tajur halang"
        and "bogor" in str(row.get("city_name", "")).strip().casefold()
        and str(row.get("province_name", "")).strip().casefold() in {"jawa barat", "west java"}
        and row.get("id") is not None
    ]
    if len(matches) != 1:
        raise HTTPException(status_code=503, detail="Lokasi gudang Sasak Panjang belum dapat diverifikasi secara unik dari RajaOngkir.")
    verified_id = str(matches[0]["id"])
    configured_id = settings.rajaongkir_origin_id.strip()
    if configured_id and configured_id != verified_id:
        raise HTTPException(status_code=503, detail="RAJAONGKIR_ORIGIN_ID tidak cocok dengan hasil pencarian gudang terverifikasi.")
    return verified_id, matches[0]

@router.get("/v1/shipping/destinations", tags=["shipping"])
async def search_shipping_destinations(search: str = Query(min_length=3, max_length=100), identity: dict[str, Any] = Depends(require_active_profile)) -> dict[str, Any]:
    if identity.get("role") != "customer":
        raise HTTPException(status_code=403, detail="Pencarian alamat pengiriman memerlukan akun pelanggan.")
    body = await rajaongkir_request("GET", "destination/domestic-destination", params={"search": search.strip(), "limit": "20", "offset": "0"})
    return {"items": [{
        "id": str(row.get("id", "")), "label": str(row.get("label") or ""),
        "province": str(row.get("province_name") or ""), "city": str(row.get("city_name") or ""),
        "district": str(row.get("district_name") or ""), "subdistrict": str(row.get("subdistrict_name") or ""),
        "postal_code": str(row.get("zip_code") or "")
    } for row in (body.get("data") or []) if row.get("id") is not None]}

@router.post("/v1/shipping/quote", tags=["shipping"])
async def quote_shipping(request: ShippingQuoteRequest = Body(...), identity: dict[str, Any] = Depends(require_active_profile)) -> dict[str, Any]:
    if identity.get("role") != "customer":
        raise HTTPException(status_code=403, detail="Kutipan ongkir memerlukan akun pelanggan.")
    origin_id, origin = await resolve_origin()
    dest_body = await rajaongkir_request("GET", "destination/domestic-destination", params={"search": request.destination_search.strip(), "limit": "50", "offset": "0"})
    dest_matches = [row for row in (dest_body.get("data") or []) if str(row.get("id")) == request.destination_id]
    if len(dest_matches) != 1:
        raise HTTPException(status_code=422, detail="Pilih alamat tujuan dari hasil pencarian RajaOngkir.")
    carts = await supabase_get("shopping_carts", {"select": "id", "customer_user_id": "eq." + str(identity["user"]["id"]), "limit": "1"}, identity["_access_token"])
    if not carts:
        raise HTTPException(status_code=422, detail="Keranjang masih kosong.")
    rows = await supabase_get("shopping_cart_items", {"select": "product_id,quantity,products(weight_grams,status)", "cart_id": "eq." + str(carts[0]["id"]), "limit": "100"}, identity["_access_token"])
    total_weight = 0
    for row in rows:
        product = row.get("products") or {}
        weight = product.get("weight_grams")
        if product.get("status") != "published" or not isinstance(weight, int) or weight <= 0:
            raise HTTPException(status_code=422, detail="Berat produk belum diisi atau belum valid. Ongkir belum dapat dihitung.")
        total_weight += weight * int(row.get("quantity", 0))
    if total_weight <= 0:
        raise HTTPException(status_code=422, detail="Keranjang kosong atau berat paket tidak valid.")
    courier = request.courier.strip().lower() if request.courier else settings.rajaongkir_default_couriers
    if any(not part.isalnum() for part in courier.split(":")):
        raise HTTPException(status_code=422, detail="Pilihan kurir tidak valid.")
    body = await rajaongkir_request("POST", "calculate/domestic-cost", data={"origin": origin_id, "destination": request.destination_id, "weight": str(total_weight), "courier": courier, "price": "lowest"})
    quotes = []
    for row in (body.get("data") or []):
        try:
            cost = int(row.get("cost"))
        except (ValueError, TypeError):
            continue
        if cost >= 0:
            quotes.append({"courier": str(row.get("code") or ""), "courier_name": str(row.get("name") or row.get("code") or ""), "service": str(row.get("service") or ""), "description": str(row.get("description") or ""), "cost": cost, "etd": str(row.get("etd") or "")})
    if not quotes:
        raise HTTPException(status_code=422, detail="Tidak ada layanan kurir untuk rute dan berat paket ini.")
    return {"origin": {"id": origin_id, "label": str(origin.get("label") or settings.rajaongkir_origin_address)}, "destination": {"id": request.destination_id, "label": str(dest_matches[0].get("label") or ""), "postal_code": str(dest_matches[0].get("zip_code") or ""), "city": str(dest_matches[0].get("city_name") or ""), "province": str(dest_matches[0].get("province_name") or "")}, "weight_grams": total_weight, "currency": "IDR", "expires_in_seconds": settings.rajaongkir_quote_ttl_seconds, "quotes": quotes}


class ShippingWeightMutation(BaseModel):
    weight_grams: int = Field(ge=1, le=1000000)

    model_config = {"extra": "forbid"}

@router.post("/v1/admin/catalog/products/{product_id}/shipping-weight", tags=["catalog"])
async def set_product_shipping_weight(
    product_id: UUID,
    request: ShippingWeightMutation = Body(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    identity: dict[str, Any] = Depends(require_roles("admin", "catalog_editor", "moderator")),
) -> dict[str, Any]:
    supabase_url, anon_key = require_supabase_configuration()
    headers = {"apikey": anon_key, "Authorization": "Bearer " + identity["_access_token"], "Content-Type": "application/json", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.post(supabase_url.rstrip("/") + "/rest/v1/rpc/oto_product_set_shipping_weight", headers=headers, json={"p_product_id": str(product_id), "p_weight_grams": request.weight_grams, "p_request_id": idempotency_key})
        if response.status_code in (401, 403):
            raise HTTPException(status_code=403, detail="Perubahan berat produk tidak diizinkan.")
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Produk tidak ditemukan.")
        if response.status_code == 429 or response.status_code >= 500:
            raise HTTPException(status_code=503, detail="Layanan katalog sedang tidak tersedia.")
        if response.status_code not in (200, 201):
            raise HTTPException(status_code=422, detail="Berat produk tidak dapat disimpan.")
        return {"result": response.json()}
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=503, detail="Penyimpanan berat produk melewati batas waktu.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Tidak dapat menghubungi layanan katalog.") from exc
