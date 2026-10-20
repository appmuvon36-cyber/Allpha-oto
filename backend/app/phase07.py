from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
import hashlib
import hmac
from urllib.parse import quote
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.main import (
    get_current_identity,
    require_active_profile,
    require_roles,
    require_supabase_configuration,
    supabase_get,
    supabase_write,
    settings,
)

router = APIRouter()


class CartMutation(BaseModel):
    action: str = Field(min_length=1, max_length=40)
    product_id: UUID | None = None
    quantity: int | None = Field(default=None, ge=1, le=100)


class ShippingAddress(BaseModel):
    recipient_name: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=6, max_length=30)
    address: str = Field(min_length=8, max_length=500)
    city: str = Field(min_length=1, max_length=100)
    province: str = Field(min_length=1, max_length=100)
    postal_code: str = Field(min_length=5, max_length=5, pattern=r"^\d{5}$")

    model_config = {"extra": "forbid"}


class ShippingQuoteSelection(BaseModel):
    destination_id: str = Field(min_length=1, max_length=32)
    destination_search: str = Field(min_length=3, max_length=100)
    courier: str = Field(min_length=2, max_length=30)
    service: str = Field(min_length=1, max_length=80)
    cost: int = Field(ge=0, le=100000000)

    model_config = {"extra": "forbid"}


class CheckoutRequest(BaseModel):
    # Cart contents and shipping fee are validated server-side.
    shipping_address: ShippingAddress
    shipping_quote: ShippingQuoteSelection | None = None
    coupon_code: str | None = Field(default=None, min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")

    model_config = {"extra": "forbid"}


class PaymentEvidence(BaseModel):
    amount: Decimal = Field(ge=0)
    method: str = Field(default="manual_transfer", pattern=r"^(manual_transfer|provider)$")
    evidence_reference: str = Field(min_length=1, max_length=1000)


class OrderMutation(BaseModel):
    action: str = Field(min_length=1, max_length=40)
    payload: dict[str, Any] = Field(default_factory=dict)


class WhatsAppHandoffMutation(BaseModel):
    action: str = Field(pattern=r"^(confirm|decline)$")
    note: str | None = Field(default=None, max_length=1000)

    model_config = {"extra": "forbid"}


async def phase07_rpc(function_name: str, body: dict[str, Any], token: str) -> Any:
    if function_name not in {"oto_inventory_mutate", "oto_order_mutate", "oto_expire_reservations", "oto_order_whatsapp_handoff", "oto_coupon_preview"}:
        raise HTTPException(status_code=422, detail="Unsupported transaction operation.")
    url, anon_key = require_supabase_configuration()
    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(f"{url}/rest/v1/rpc/{function_name}", headers=headers, json=body)
        if response.status_code in (401, 403):
            raise HTTPException(status_code=403, detail="Transaction operation is not permitted.")
        if response.status_code == 429 or response.status_code >= 500:
            raise HTTPException(status_code=503, detail="Transaction service is temporarily unavailable.")
        if response.status_code not in (200, 201):
            try:
                error = response.json()
                message, code = str(error.get("message", "")), str(error.get("code", ""))
            except (ValueError, AttributeError):
                message, code = "", ""
            if code == "P0002" or "not_found" in message:
                raise HTTPException(status_code=404, detail="The requested record was not found.")
            if code == "42501" or "ownership_required" in message or "role_required" in message:
                raise HTTPException(status_code=403, detail="Transaction operation is not permitted for this account.")
            if code == "23505" or "already_exists" in message:
                raise HTTPException(status_code=409, detail="A conflicting transaction already exists.")
            if code in {"22023", "22P02", "23514", "23502"}:
                raise HTTPException(status_code=422, detail="Transaction validation failed.")
            raise HTTPException(status_code=503, detail="Transaction could not be completed.")
        return response.json()
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=503, detail="Transaction service timed out.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Could not reach transaction service.") from exc


async def order_rpc(action: str, order_id: UUID | None, payload: dict[str, Any], request_id: str, identity: dict[str, Any]) -> Any:
    return await phase07_rpc(
        "oto_order_mutate",
        {
            "p_action": action,
            "p_order_id": str(order_id) if order_id else None,
            "p_payload": payload,
            "p_request_id": request_id,
        },
        identity["_access_token"],
    )


@router.get("/v1/cart", tags=["cart"])
async def get_cart(identity: dict[str, Any] = Depends(require_active_profile)) -> dict[str, Any]:
    user_id = identity["user"]["id"]
    carts = await supabase_get("shopping_carts", {"select": "id,updated_at", "customer_user_id": f"eq.{user_id}", "limit": "1"}, identity["_access_token"])
    if not carts:
        return {"items": [], "count": 0, "subtotal": 0}
    rows = await supabase_get(
        "shopping_cart_items",
        {"select": "id,product_id,quantity,updated_at,products(id,sku,name,brand,part_number,condition,package_quantity,warranty_days,retail_price,currency,status)",
         "cart_id": f"eq.{carts[0]['id']}", "order": "updated_at.desc", "limit": "100"},
        identity["_access_token"],
    )
    items = []
    subtotal = Decimal("0")
    for row in rows:
        product = row.get("products") or {}
        if product.get("status") != "published" or product.get("retail_price") is None:
            continue
        price = Decimal(str(product["retail_price"]))
        quantity = int(row["quantity"])
        subtotal += price * quantity
        items.append({**row, "line_total": str(price * quantity)})
    return {"items": items, "count": len(items), "subtotal": str(subtotal), "currency": "IDR"}


@router.post("/v1/cart/mutations", tags=["cart"])
async def mutate_cart(
    mutation: CartMutation = Body(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    identity: dict[str, Any] = Depends(require_active_profile),
) -> dict[str, Any]:
    if identity.get("role") != "customer":
        raise HTTPException(status_code=403, detail="Cart actions require a customer account.")
    if mutation.action not in {"cart_add", "cart_set_quantity", "cart_remove", "cart_clear"}:
        raise HTTPException(status_code=422, detail="Unsupported cart action.")
    payload: dict[str, Any] = {}
    if mutation.product_id:
        payload["product_id"] = str(mutation.product_id)
    if mutation.quantity is not None:
        payload["quantity"] = mutation.quantity
    result = await order_rpc(mutation.action, None, payload, idempotency_key, identity)
    return {"result": result}


@router.post("/v1/checkout", tags=["orders"])
async def checkout(
    request: CheckoutRequest = Body(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    identity: dict[str, Any] = Depends(require_active_profile),
) -> dict[str, Any]:
    if identity.get("role") != "customer":
        raise HTTPException(status_code=403, detail="Checkout requires a customer account.")

    if request.shipping_quote is None:
        raise HTTPException(status_code=422, detail="Pilih layanan ongkir RajaOngkir sebelum checkout.")
    # Recalculate the selected service on the server; never trust a client price.
    from app.shipping import ShippingQuoteRequest, quote_shipping
    live_quote = await quote_shipping(
        ShippingQuoteRequest(
            destination_id=request.shipping_quote.destination_id,
            destination_search=request.shipping_quote.destination_search,
            courier=request.shipping_quote.courier,
        ),
        identity,
    )
    address_postal = (request.shipping_address.postal_code or "").strip()
    quote_postal = str(live_quote["destination"].get("postal_code") or "").strip()
    if not address_postal or len(address_postal) != 5 or not address_postal.isdigit():
        raise HTTPException(status_code=422, detail="Kode pos Indonesia 5 digit wajib diisi.")
    if quote_postal and address_postal != quote_postal:
        raise HTTPException(status_code=422, detail="Kode pos alamat tidak cocok dengan lokasi tujuan ongkir.")
    address_city = request.shipping_address.city.strip().casefold()
    address_province = request.shipping_address.province.strip().casefold()
    quote_city = str(live_quote["destination"].get("city") or "").strip().casefold()
    quote_province = str(live_quote["destination"].get("province") or "").strip().casefold()
    if (address_city not in quote_city and quote_city not in address_city) or (address_province not in quote_province and quote_province not in address_province):
        raise HTTPException(status_code=422, detail="Kota/provinsi alamat harus cocok dengan lokasi tujuan ongkir.")
    selected = next(
        (q for q in live_quote["quotes"]
         if q["courier"].casefold() == request.shipping_quote.courier.casefold()
         and q["service"].casefold() == request.shipping_quote.service.casefold()),
        None,
    )
    if selected is None or selected["cost"] != request.shipping_quote.cost:
        raise HTTPException(status_code=409, detail="Tarif ongkir berubah. Hitung ulang dan pilih layanan kembali.")
    server_shipping_fee = int(selected["cost"])

    carts = await supabase_get(
        "shopping_carts",
        {"select": "id", "customer_user_id": f"eq.{identity['user']['id']}", "limit": "1"},
        identity["_access_token"],
    )
    if not carts:
        raise HTTPException(status_code=422, detail="Keranjang masih kosong.")
    cart_rows = await supabase_get(
        "shopping_cart_items",
        {"select": "product_id,quantity", "cart_id": f"eq.{carts[0]['id']}", "limit": "50"},
        identity["_access_token"],
    )
    normalized: list[dict[str, Any]] = []
    seen_product_ids: set[str] = set()
    for item in cart_rows:
        try:
            product_id = str(UUID(str(item["product_id"])))
            quantity = int(item["quantity"])
        except (KeyError, ValueError, TypeError):
            raise HTTPException(status_code=422, detail="Item keranjang tidak valid.")
        if product_id in seen_product_ids or quantity < 1 or quantity > 100:
            raise HTTPException(status_code=422, detail="Item keranjang duplikat atau jumlahnya tidak valid.")
        seen_product_ids.add(product_id)
        normalized.append({"product_id": product_id, "quantity": quantity})
    if not normalized:
        raise HTTPException(status_code=422, detail="Keranjang masih kosong.")
    if not settings.rajaongkir_quote_signing_secret:
        raise HTTPException(status_code=503, detail="Checkout menunggu konfigurasi keamanan kutipan ongkir.")
    quoted_at = datetime.now(timezone.utc).isoformat()
    quote_snapshot = {
        "provider": "rajaongkir",
        "origin_id": live_quote["origin"]["id"],
        "origin_label": live_quote["origin"]["label"],
        "destination_id": live_quote["destination"]["id"],
        "destination_label": live_quote["destination"]["label"],
        "courier": selected["courier"],
        "courier_name": selected["courier_name"],
        "service": selected["service"],
        "description": selected["description"],
        "cost": server_shipping_fee,
        "weight_grams": live_quote["weight_grams"],
        "quoted_at": quoted_at,
        "expires_in_seconds": live_quote["expires_in_seconds"],
    }
    signed_fields = "|".join([
        str(identity["user"]["id"]), str(quote_snapshot["origin_id"]),
        str(quote_snapshot["destination_id"]), str(quote_snapshot["courier"]),
        str(quote_snapshot["service"]), str(quote_snapshot["cost"]),
        str(quote_snapshot["weight_grams"]), quoted_at,
        str(quote_snapshot["expires_in_seconds"]),
    ])
    signature = hmac.new(
        settings.rajaongkir_quote_signing_secret.encode("utf-8"),
        signed_fields.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    shipping_address_snapshot = request.shipping_address.model_dump(mode="json", exclude_none=True)
    shipping_address_snapshot["shipping_quote"] = quote_snapshot
    result = await order_rpc("checkout", None, {
        "items": normalized,
        "shipping_address": shipping_address_snapshot,
        "shipping_fee": str(server_shipping_fee),
        "shipping_quote": {**quote_snapshot, "signature": signature},
        "coupon_code": request.coupon_code.strip().upper() if request.coupon_code else None,
    }, idempotency_key, identity)
    return {"result": result}


@router.get("/v1/orders", tags=["orders"])
async def list_customer_orders(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
    identity: dict[str, Any] = Depends(require_active_profile),
) -> dict[str, Any]:
    rows = await supabase_get(
        "oto_orders",
        {"select": "id,status,subtotal,shipping_fee,total_amount,currency,tracking_code,sales_channel,whatsapp_handoff_status,whatsapp_handoff_prepared_at,whatsapp_handoff_expires_at,shipped_at,delivered_at,created_at,updated_at",
         "customer_user_id": f"eq.{identity['user']['id']}", "order": "created_at.desc", "limit": str(limit), "offset": str(offset)},
        identity["_access_token"],
    )
    return {"items": rows, "count": len(rows), "limit": limit, "offset": offset, "next_offset": offset + limit if len(rows) == limit else None}


@router.get("/v1/orders/{order_id}", tags=["orders"])
async def get_order(order_id: UUID, identity: dict[str, Any] = Depends(require_active_profile)) -> dict[str, Any]:
    rows = await supabase_get(
        "oto_orders",
        {"select": "id,customer_user_id,status,subtotal,shipping_fee,total_amount,currency,shipping_address,tracking_code,shipping_carrier,shipping_service,shipping_exception_code,shipping_exception_note,shipping_last_event_at,sales_channel,whatsapp_handoff_status,whatsapp_handoff_prepared_at,whatsapp_handoff_expires_at,whatsapp_handoff_reviewed_at,whatsapp_handoff_review_note,shipped_at,delivered_at,cancelled_at,created_at,updated_at",
         "id": f"eq.{order_id}", "limit": "1"},
        identity["_access_token"],
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan.")
    order = rows[0]
    items = await supabase_get("oto_order_items", {"select": "id,product_id,sku_snapshot,name_snapshot,condition_snapshot,unit_price,quantity,line_total", "order_id": f"eq.{order_id}", "limit": "100"}, identity["_access_token"])
    payments = await supabase_get("oto_payment_events", {"select": "id,event_type,amount,method,provider_reference,status,review_note,reviewed_at,created_at", "order_id": f"eq.{order_id}", "order": "created_at.desc", "limit": "50"}, identity["_access_token"])
    returns = await supabase_get("oto_returns", {"select": "id,status,reason,requested_refund,refund_provider_reference,created_at,updated_at", "order_id": f"eq.{order_id}", "limit": "10"}, identity["_access_token"])
    fulfillment = await supabase_get("oto_fulfillment_events", {"select": "id,event_type,from_status,to_status,carrier,service,tracking_code,note,created_at", "order_id": f"eq.{order_id}", "order": "created_at.desc", "limit": "100"}, identity["_access_token"])
    return {"order": order, "items": items, "payments": payments, "returns": returns, "fulfillment_events": list(reversed(fulfillment))}


@router.post("/v1/orders/{order_id}/whatsapp-handoff", tags=["orders"])
async def prepare_whatsapp_handoff(
    order_id: UUID,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    identity: dict[str, Any] = Depends(require_active_profile),
) -> dict[str, Any]:
    if identity.get("role") != "customer":
        raise HTTPException(status_code=403, detail="WhatsApp handoff requires a customer account.")
    # Deep links do not require the Cloud API, but must point to the configured
    # official business number. Never guess or silently route to a random contact.
    phone = "".join(ch for ch in settings.whatsapp_business_phone if ch.isdigit())
    if phone.startswith("0"):
        phone = "62" + phone[1:]
    if not phone or len(phone) < 8 or len(phone) > 15:
        raise HTTPException(status_code=503, detail="Kanal WhatsApp OtoClinic belum dikonfigurasi.")
    result = await phase07_rpc(
        "oto_order_whatsapp_handoff",
        {"p_action": "prepare", "p_order_id": str(order_id), "p_payload": {}, "p_request_id": idempotency_key},
        identity["_access_token"],
    )
    order = result.get("order") if isinstance(result, dict) else None
    if not isinstance(order, dict) or str(order.get("id")) != str(order_id):
        raise HTTPException(status_code=409, detail="Referensi pesanan WhatsApp tidak dapat disiapkan.")
    items = await supabase_get(
        "oto_order_items",
        {"select": "product_id,sku_snapshot,name_snapshot,condition_snapshot,quantity,unit_price,line_total", "order_id": f"eq.{order_id}", "limit": "50"},
        identity["_access_token"],
    )
    if not items:
        raise HTTPException(status_code=409, detail="Rincian pesanan tidak tersedia untuk handoff.")

    # Enrich the canonical order-item snapshots with the published catalog details
    # that customers see on the product page. Price/quantity/totals remain from the order.
    product_ids = sorted({str(item.get("product_id")) for item in items if item.get("product_id")})
    product_rows: list[dict[str, Any]] = []
    if product_ids:
        product_rows = await supabase_get(
            "products",
            {
                "select": "id,description,brand,part_number,category,package_quantity,warranty_days",
                "id": "in.(" + ",".join(product_ids) + ")",
                "status": "eq.published",
                "limit": "50",
            },
            identity["_access_token"],
        )
    products_by_id = {str(product.get("id")): product for product in product_rows}

    def format_idr(value: Any) -> str:
        return "Rp" + f"{int(Decimal(str(value or 0))):,}".replace(",", ".")

    detail_lines: list[str] = []
    for item in items:
        product = products_by_id.get(str(item.get("product_id")), {})
        name = str(item.get("name_snapshot") or "Produk")
        sku = str(item.get("sku_snapshot") or "-")
        quantity = int(item.get("quantity") or 0)
        detail_lines.append(f"- {name}")
        detail_lines.append(f"  SKU: {sku}")
        if product.get("part_number"):
            detail_lines.append(f"  Nomor part: {str(product['part_number'])[:120]}")
        if product.get("brand"):
            detail_lines.append(f"  Merek: {str(product['brand'])[:120]}")
        if item.get("condition_snapshot"):
            detail_lines.append(f"  Kondisi: {str(item['condition_snapshot'])}")
        description = " ".join(str(product.get("description") or "").split())
        if description:
            detail_lines.append(f"  Deskripsi: {description[:500]}")
        if product.get("category"):
            detail_lines.append(f"  Kategori: {str(product['category'])[:120]}")
        if product.get("package_quantity") is not None:
            detail_lines.append(f"  Isi kemasan: {int(product['package_quantity'])} unit")
        if product.get("warranty_days") is not None:
            warranty_days = int(product["warranty_days"])
            detail_lines.append(f"  Garansi: {str(warranty_days) + ' hari' if warranty_days > 0 else 'belum dicantumkan'}")
        detail_lines.append(f"  Jumlah: {quantity}")
        detail_lines.append(f"  Harga satuan: {format_idr(item.get('unit_price'))}")
        detail_lines.append(f"  Total item: {format_idr(item.get('line_total'))}")

    message = "\n".join([
        "Halo OtoClinic, saya ingin menindaklanjuti pesanan yang sudah tercatat di website.",
        f"Referensi pesanan: {order_id}",
        f"Tanggal pesanan: {str(order.get('created_at') or '-')}",
        f"Status pesanan: {str(order.get('status') or 'pending_payment')}",
        "",
        "DETAIL PRODUK:",
        *detail_lines,
        "",
        f"Subtotal: {format_idr(order.get('subtotal'))}",
        f"Ongkir tercatat: {format_idr(order.get('shipping_fee'))}",
        f"TOTAL PESANAN: {format_idr(order.get('total_amount'))}",
        "",
        "Mohon konfirmasi ketersediaan barang, informasi pembayaran, dan estimasi pengiriman.",
        "Catatan: pesan ini bukan bukti pembayaran. Status pembayaran tetap mengikuti sistem OtoClinic.",
    ])
    return {
        "result": result,
        "whatsapp_url": f"https://wa.me/{phone}?text={quote(message, safe='')}",
        "handoff_notice": "Tautan WhatsApp disiapkan. Ini tidak membuktikan pesan telah dikirim atau diterima.",
    }


@router.post("/v1/admin/orders/{order_id}/whatsapp-handoff", tags=["orders"])
async def review_whatsapp_handoff(
    order_id: UUID,
    request: WhatsAppHandoffMutation = Body(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    identity: dict[str, Any] = Depends(require_roles("admin", "order_manager")),
) -> dict[str, Any]:
    result = await phase07_rpc(
        "oto_order_whatsapp_handoff",
        {"p_action": request.action, "p_order_id": str(order_id), "p_payload": {"note": request.note} if request.note else {}, "p_request_id": idempotency_key},
        identity["_access_token"],
    )
    return {"result": result}


@router.post("/v1/orders/{order_id}/payment-evidence", tags=["payments"])
async def submit_payment_evidence(
    order_id: UUID,
    request: PaymentEvidence = Body(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    identity: dict[str, Any] = Depends(require_active_profile),
) -> dict[str, Any]:
    if identity.get("role") != "customer":
        raise HTTPException(status_code=403, detail="Payment evidence requires a customer account.")
    result = await order_rpc("submit_payment_evidence", order_id, request.model_dump(mode="json"), idempotency_key, identity)
    return {"result": result}


@router.post("/v1/orders/{order_id}/cancel", tags=["orders"])
async def cancel_order(
    order_id: UUID,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    identity: dict[str, Any] = Depends(require_active_profile),
) -> dict[str, Any]:
    return {"result": await order_rpc("cancel_order", order_id, {}, idempotency_key, identity)}


@router.post("/v1/orders/{order_id}/returns", tags=["returns"])
async def request_return(
    order_id: UUID,
    request: dict[str, Any] = Body(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    identity: dict[str, Any] = Depends(require_active_profile),
) -> dict[str, Any]:
    if identity.get("role") != "customer":
        raise HTTPException(status_code=403, detail="Return requests require a customer account.")
    if len(str(request)) > 20000:
        raise HTTPException(status_code=413, detail="Return request is too large.")
    return {"result": await order_rpc("request_return", order_id, request, idempotency_key, identity)}


@router.get("/v1/admin/inventory", tags=["inventory"])
async def list_inventory(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10000),
    identity: dict[str, Any] = Depends(require_roles("admin", "inventory_manager", "order_manager")),
) -> dict[str, Any]:
    rows = await supabase_get(
        "inventory_balances",
        {"select": "product_id,on_hand,reserved,updated_at,products(id,sku,name,part_number,condition,retail_price,status)",
         "order": "updated_at.desc", "limit": str(limit), "offset": str(offset)},
        identity["_access_token"],
    )
    return {"items": rows, "count": len(rows), "limit": limit, "offset": offset, "next_offset": offset + limit if len(rows) == limit else None}


@router.get("/v1/admin/inventory/ledger", tags=["inventory"])
async def list_inventory_ledger(
    product_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10000),
    identity: dict[str, Any] = Depends(require_roles("admin", "inventory_manager", "order_manager")),
) -> dict[str, Any]:
    params = {"select": "id,product_id,supplier_id,movement,quantity_delta,reference_type,reference_id,reason,actor_user_id,created_at",
              "order": "created_at.desc", "limit": str(limit), "offset": str(offset)}
    if product_id:
        params["product_id"] = f"eq.{product_id}"
    rows = await supabase_get("inventory_ledger", params, identity["_access_token"])
    return {"items": rows, "count": len(rows), "limit": limit, "offset": offset, "next_offset": offset + limit if len(rows) == limit else None}


@router.post("/v1/admin/inventory/mutations", tags=["inventory"])
async def mutate_inventory(
    request: dict[str, Any] = Body(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    identity: dict[str, Any] = Depends(require_roles("admin", "inventory_manager")),
) -> dict[str, Any]:
    action = request.get("action")
    allowed = {"receipt", "adjustment_increase", "adjustment_decrease", "write_off"}
    if action not in allowed:
        raise HTTPException(status_code=422, detail="Unsupported inventory action.")
    product_id = request.get("product_id")
    try:
        product_uuid = UUID(str(product_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Product ID is invalid.")
    payload = request.get("payload", {})
    if not isinstance(payload, dict) or len(str(payload)) > 10000:
        raise HTTPException(status_code=422, detail="Inventory payload is invalid.")
    result = await phase07_rpc("oto_inventory_mutate", {
        "p_action": action, "p_product_id": str(product_uuid), "p_payload": payload, "p_request_id": idempotency_key,
    }, identity["_access_token"])
    return {"result": result}


@router.get("/v1/admin/orders", tags=["orders"])
async def list_admin_orders(
    status: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10000),
    identity: dict[str, Any] = Depends(require_roles("admin", "order_manager")),
) -> dict[str, Any]:
    allowed = {"pending_payment","payment_review","paid","processing","shipped","delivered","cancelled","return_requested","returned","partially_returned"}
    if status and status not in allowed:
        raise HTTPException(status_code=422, detail="Order status filter is invalid.")
    params = {"select": "id,customer_user_id,status,subtotal,shipping_fee,total_amount,currency,tracking_code,shipping_carrier,shipping_service,shipping_exception_code,shipping_exception_note,shipping_last_event_at,sales_channel,whatsapp_handoff_status,whatsapp_handoff_prepared_at,whatsapp_handoff_expires_at,whatsapp_handoff_reviewed_at,whatsapp_handoff_review_note,created_at,updated_at",
              "order": "created_at.desc", "limit": str(limit), "offset": str(offset)}
    if status:
        params["status"] = f"eq.{status}"
    rows = await supabase_get("oto_orders", params, identity["_access_token"])
    return {"items": rows, "count": len(rows), "limit": limit, "offset": offset, "next_offset": offset + limit if len(rows) == limit else None}


@router.get("/v1/admin/payments", tags=["payments"])
async def list_admin_payments(
    status: str | None = Query(default="pending_review", max_length=32),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10000),
    identity: dict[str, Any] = Depends(require_roles("admin", "order_manager")),
) -> dict[str, Any]:
    allowed = {"pending_review","verified","rejected","refund_pending","refunded"}
    if status and status not in allowed:
        raise HTTPException(status_code=422, detail="Payment status filter is invalid.")
    params = {"select": "id,order_id,event_type,submitted_by,amount,method,provider_reference,evidence_reference,status,reviewed_by,reviewed_at,review_note,created_at",
              "order": "created_at.asc", "limit": str(limit), "offset": str(offset)}
    if status:
        params["status"] = f"eq.{status}"
    rows = await supabase_get("oto_payment_events", params, identity["_access_token"])
    return {"items": rows, "count": len(rows), "limit": limit, "offset": offset, "next_offset": offset + limit if len(rows) == limit else None}


@router.get("/v1/admin/returns", tags=["returns"])
async def list_admin_returns(
    status: str | None = Query(default="requested", max_length=32),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10000),
    identity: dict[str, Any] = Depends(require_roles("admin", "order_manager")),
) -> dict[str, Any]:
    allowed = {"requested","approved","rejected","received","refund_pending","refunded"}
    if status and status not in allowed:
        raise HTTPException(status_code=422, detail="Return status filter is invalid.")
    params = {"select": "id,order_id,customer_user_id,status,reason,requested_refund,refund_provider_reference,reviewed_by,reviewed_at,received_by,received_at,refunded_at,created_at,updated_at",
              "order": "created_at.asc", "limit": str(limit), "offset": str(offset)}
    if status:
        params["status"] = f"eq.{status}"
    rows = await supabase_get("oto_returns", params, identity["_access_token"])
    return {"items": rows, "count": len(rows), "limit": limit, "offset": offset, "next_offset": offset + limit if len(rows) == limit else None}


@router.post("/v1/admin/orders/{order_id}/mutations", tags=["orders"])
async def mutate_order(
    order_id: UUID,
    mutation: OrderMutation = Body(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    identity: dict[str, Any] = Depends(require_roles("admin", "order_manager")),
) -> dict[str, Any]:
    allowed = {"verify_payment","reject_payment","cancel_order","start_fulfillment","mark_shipped","mark_delivered","approve_return","reject_return","receive_return","record_refund"}
    if mutation.action not in allowed:
        raise HTTPException(status_code=422, detail="Unsupported order operation.")
    if len(str(mutation.payload)) > 20000:
        raise HTTPException(status_code=413, detail="Order payload is too large.")
    return {"result": await order_rpc(mutation.action, order_id, mutation.payload, idempotency_key, identity)}


@router.post("/v1/admin/orders/{order_id}/fulfillment", tags=["fulfillment"])
async def mutate_fulfillment(
    order_id: UUID,
    mutation: OrderMutation = Body(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    identity: dict[str, Any] = Depends(require_roles("admin", "order_manager")),
) -> dict[str, Any]:
    allowed = {"start_fulfillment", "pack_order", "mark_shipped", "mark_delivered", "record_exception", "resolve_exception", "update_tracking"}
    if mutation.action not in allowed:
        raise HTTPException(status_code=422, detail="Unsupported fulfillment operation.")
    if len(str(mutation.payload)) > 10000:
        raise HTTPException(status_code=413, detail="Fulfillment payload is too large.")
    return {"result": await phase07_rpc("oto_fulfillment_mutate", {
        "p_order_id": str(order_id), "p_action": mutation.action,
        "p_payload": mutation.payload, "p_request_id": idempotency_key,
    }, identity["_access_token"])}


@router.post("/v1/admin/inventory/expire-reservations", tags=["inventory"])
async def expire_inventory_reservations(
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    identity: dict[str, Any] = Depends(require_roles("admin", "inventory_manager", "order_manager")),
) -> dict[str, Any]:
    result = await phase07_rpc(
        "oto_expire_reservations",
        {"p_request_id": idempotency_key},
        identity["_access_token"],
    )
    return {"result": result}


# EC-06 — customer lifecycle and commercial rules
class SavedVehicleCreate(BaseModel):
    nickname: str = Field(min_length=1, max_length=80)
    make_id: UUID | None = None
    model_id: UUID | None = None
    variant_id: UUID | None = None
    model_year: int | None = Field(default=None, ge=1950, le=2100)
    plate_label: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=500)
    model_config = {"extra": "forbid"}


class CouponCreate(BaseModel):
    code: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    description: str | None = Field(default=None, max_length=500)
    discount_type: str = Field(pattern=r"^(fixed|percent)$")
    discount_value: Decimal = Field(gt=0, le=100000000)
    max_discount: Decimal | None = Field(default=None, gt=0)
    minimum_subtotal: Decimal = Field(default=Decimal("0"), ge=0)
    starts_at: datetime
    ends_at: datetime | None = None
    usage_limit: int | None = Field(default=None, ge=1, le=10000000)
    per_customer_limit: int = Field(default=1, ge=1, le=100000)
    is_active: bool = False
    is_public: bool = False
    model_config = {"extra": "forbid"}


class CouponPreview(BaseModel):
    code: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    subtotal: Decimal = Field(ge=0, le=100000000000)
    model_config = {"extra": "forbid"}


@router.post("/v1/coupons/preview", tags=["commercial"])
async def preview_coupon(request: CouponPreview, identity: dict[str, Any] = Depends(require_roles("customer"))) -> dict[str, Any]:
    result = await phase07_rpc("oto_coupon_preview", {"p_code": request.code.strip().upper(), "p_subtotal": str(request.subtotal)}, identity["_access_token"])
    return {"coupon": result}


@router.get("/v1/admin/coupons", tags=["commercial"])
async def admin_list_coupons(identity: dict[str, Any] = Depends(require_roles("admin", "order_manager"))) -> dict[str, Any]:
    rows = await supabase_get("oto_coupons", {"select": "id,code,description,discount_type,discount_value,max_discount,minimum_subtotal,starts_at,ends_at,usage_limit,per_customer_limit,is_active,is_public,created_at,updated_at", "order": "created_at.desc", "limit": "200"}, identity["_access_token"])
    return {"items": rows, "count": len(rows)}


@router.post("/v1/admin/coupons", tags=["commercial"], status_code=201)
async def admin_create_coupon(request: CouponCreate, identity: dict[str, Any] = Depends(require_roles("admin", "order_manager"))) -> dict[str, Any]:
    payload = request.model_dump(mode="json")
    payload["code"] = request.code.strip().upper()
    payload["created_by"] = identity["user"]["id"]
    rows = await supabase_write("POST", "oto_coupons", identity["_access_token"], payload)
    if not rows:
        raise HTTPException(status_code=503, detail="Coupon could not be saved.")
    return {"coupon": rows[0]}


@router.patch("/v1/admin/coupons/{coupon_id}", tags=["commercial"])
async def admin_update_coupon(coupon_id: UUID, request: dict[str, Any] = Body(...), identity: dict[str, Any] = Depends(require_roles("admin", "order_manager"))) -> dict[str, Any]:
    allowed = {"description", "discount_type", "discount_value", "max_discount", "minimum_subtotal", "starts_at", "ends_at", "usage_limit", "per_customer_limit", "is_active", "is_public"}
    if not request or set(request) - allowed:
        raise HTTPException(status_code=422, detail="Unsupported coupon fields.")
    if "discount_type" in request and request["discount_type"] not in {"fixed", "percent"}:
        raise HTTPException(status_code=422, detail="Invalid discount type.")
    payload = dict(request)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    rows = await supabase_write("PATCH", "oto_coupons", identity["_access_token"], payload, {"id": f"eq.{coupon_id}"})
    if not rows:
        raise HTTPException(status_code=404, detail="Coupon not found.")
    return {"coupon": rows[0]}


@router.get("/v1/wishlist", tags=["customer-lifecycle"])
async def list_wishlist(identity: dict[str, Any] = Depends(require_roles("customer"))) -> dict[str, Any]:
    rows = await supabase_get("oto_wishlist_items", {"select": "id,product_id,created_at,products(id,sku,name,brand,part_number,condition,retail_price,currency,status)", "customer_user_id": f"eq.{identity['user']['id']}", "order": "created_at.desc", "limit": "200"}, identity["_access_token"])
    return {"items": [r for r in rows if (r.get("products") or {}).get("status") == "published"], "count": len(rows)}


@router.post("/v1/wishlist/{product_id}", tags=["customer-lifecycle"], status_code=201)
async def add_wishlist(product_id: UUID, identity: dict[str, Any] = Depends(require_roles("customer"))) -> dict[str, Any]:
    product = await supabase_get("products", {"select": "id,status", "id": f"eq.{product_id}", "status": "eq.published", "limit": "1"}, identity["_access_token"])
    if not product:
        raise HTTPException(status_code=404, detail="Published product not found.")
    try:
        rows = await supabase_write("POST", "oto_wishlist_items", identity["_access_token"], {"customer_user_id": identity["user"]["id"], "product_id": str(product_id)})
    except HTTPException as exc:
        if exc.status_code != 409:
            raise
        rows = await supabase_get("oto_wishlist_items", {"select": "id,product_id,created_at", "customer_user_id": f"eq.{identity['user']['id']}", "product_id": f"eq.{product_id}", "limit": "1"}, identity["_access_token"])
        return {"item": rows[0] if rows else None, "replayed": True}
    return {"item": rows[0] if rows else None, "replayed": False}


@router.delete("/v1/wishlist/{product_id}", tags=["customer-lifecycle"])
async def remove_wishlist(product_id: UUID, identity: dict[str, Any] = Depends(require_roles("customer"))) -> dict[str, Any]:
    url, anon_key = require_supabase_configuration()
    headers = {"apikey": anon_key, "Authorization": f"Bearer {identity['_access_token']}", "Prefer": "return=minimal"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.delete(f"{url}/rest/v1/oto_wishlist_items", params={"customer_user_id": f"eq.{identity['user']['id']}", "product_id": f"eq.{product_id}"}, headers=headers)
    if response.status_code not in (200, 204):
        raise HTTPException(status_code=503, detail="Wishlist update failed.")
    return {"removed": True}


@router.get("/v1/saved-vehicles", tags=["customer-lifecycle"])
async def list_saved_vehicles(identity: dict[str, Any] = Depends(require_roles("customer"))) -> dict[str, Any]:
    rows = await supabase_get("oto_saved_vehicles", {"select": "id,nickname,make_id,model_id,variant_id,model_year,plate_label,notes,created_at,updated_at", "customer_user_id": f"eq.{identity['user']['id']}", "order": "created_at.desc", "limit": "100"}, identity["_access_token"])
    return {"items": rows, "count": len(rows)}


@router.post("/v1/saved-vehicles", tags=["customer-lifecycle"], status_code=201)
async def create_saved_vehicle(request: SavedVehicleCreate, identity: dict[str, Any] = Depends(require_roles("customer"))) -> dict[str, Any]:
    if not any((request.make_id, request.model_id, request.variant_id)):
        raise HTTPException(status_code=422, detail="Pilih minimal merek, model, atau varian kendaraan.")
    rows = await supabase_write("POST", "oto_saved_vehicles", identity["_access_token"], {**request.model_dump(mode="json"), "customer_user_id": identity["user"]["id"]})
    if not rows:
        raise HTTPException(status_code=503, detail="Saved vehicle could not be saved.")
    return {"vehicle": rows[0]}


@router.patch("/v1/saved-vehicles/{vehicle_id}", tags=["customer-lifecycle"])
async def update_saved_vehicle(vehicle_id: UUID, request: SavedVehicleCreate, identity: dict[str, Any] = Depends(require_roles("customer"))) -> dict[str, Any]:
    payload = request.model_dump(mode="json")
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    rows = await supabase_write("PATCH", "oto_saved_vehicles", identity["_access_token"], payload, {"id": f"eq.{vehicle_id}", "customer_user_id": f"eq.{identity['user']['id']}"})
    if not rows:
        raise HTTPException(status_code=404, detail="Saved vehicle not found.")
    return {"vehicle": rows[0]}


@router.delete("/v1/saved-vehicles/{vehicle_id}", tags=["customer-lifecycle"])
async def delete_saved_vehicle(vehicle_id: UUID, identity: dict[str, Any] = Depends(require_roles("customer"))) -> dict[str, Any]:
    url, anon_key = require_supabase_configuration()
    headers = {"apikey": anon_key, "Authorization": f"Bearer {identity['_access_token']}", "Prefer": "return=minimal"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.delete(f"{url}/rest/v1/oto_saved_vehicles", params={"id": f"eq.{vehicle_id}", "customer_user_id": f"eq.{identity['user']['id']}"}, headers=headers)
    if response.status_code not in (200, 204):
        raise HTTPException(status_code=503, detail="Saved vehicle update failed.")
    return {"deleted": True}


@router.get("/v1/notifications", tags=["customer-lifecycle"])
async def list_notifications(unread_only: bool = Query(default=False), identity: dict[str, Any] = Depends(require_active_profile)) -> dict[str, Any]:
    params = {"select": "id,event_type,title,body,resource_type,resource_id,read_at,created_at", "customer_user_id": f"eq.{identity['user']['id']}", "order": "created_at.desc", "limit": "100"}
    if unread_only:
        params["read_at"] = "is.null"
    rows = await supabase_get("oto_notifications", params, identity["_access_token"])
    return {"items": rows, "unread_count": sum(1 for r in rows if r.get("read_at") is None)}


@router.post("/v1/notifications/{notification_id}/read", tags=["customer-lifecycle"])
async def mark_notification_read(notification_id: UUID, identity: dict[str, Any] = Depends(require_active_profile)) -> dict[str, Any]:
    rows = await supabase_write("PATCH", "oto_notifications", identity["_access_token"], {"read_at": datetime.now(timezone.utc).isoformat()}, {"id": f"eq.{notification_id}", "customer_user_id": f"eq.{identity['user']['id']}"})
    if not rows:
        raise HTTPException(status_code=404, detail="Notification not found.")
    return {"notification": rows[0]}


@router.post("/v1/orders/{order_id}/reorder", tags=["customer-lifecycle"])
async def reorder(order_id: UUID, idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128), identity: dict[str, Any] = Depends(require_roles("customer"))) -> dict[str, Any]:
    orders = await supabase_get("oto_orders", {"select": "id,customer_user_id", "id": f"eq.{order_id}", "customer_user_id": f"eq.{identity['user']['id']}", "limit": "1"}, identity["_access_token"])
    if not orders:
        raise HTTPException(status_code=404, detail="Order not found.")
    items = await supabase_get("oto_order_items", {"select": "product_id,quantity", "order_id": f"eq.{order_id}", "limit": "100"}, identity["_access_token"])
    if not items:
        raise HTTPException(status_code=422, detail="Order has no items to reorder.")
    added=[]; unavailable=[]
    carts=await supabase_get("shopping_carts", {"select":"id","customer_user_id":f"eq.{identity['user']['id']}","limit":"1"}, identity["_access_token"])
    existing={}
    if carts:
        existing_rows=await supabase_get("shopping_cart_items", {"select":"product_id,quantity","cart_id":f"eq.{carts[0]['id']}","limit":"100"}, identity["_access_token"])
        existing={str(row["product_id"]):int(row["quantity"]) for row in existing_rows}
    for item in items:
        pid=str(item["product_id"]); qty=int(item["quantity"])
        product=await supabase_get("products", {"select":"id,status,retail_price", "id":f"eq.{pid}", "status":"eq.published", "limit":"1"}, identity["_access_token"])
        if not product or product[0].get("retail_price") is None:
            unavailable.append({"product_id":pid,"reason":"not_published"})
            continue
        desired=min(100,qty+existing.get(pid,0))
        stock=await supabase_get("inventory_balances", {"select":"on_hand,reserved","product_id":f"eq.{pid}","limit":"1"}, identity["_access_token"])
        if not stock or int(stock[0].get("on_hand",0))-int(stock[0].get("reserved",0))<desired:
            unavailable.append({"product_id":pid,"reason":"insufficient_or_unverified_stock"})
            continue
        await order_rpc("cart_set_quantity", None, {"product_id":pid,"quantity":desired}, f"{idempotency_key[:80]}:{pid[:32]}", identity)
        added.append({"product_id":pid,"quantity":desired})
    return {"added":added,"unavailable":unavailable,"message":"Item yang tersedia dimasukkan ke keranjang; periksa harga dan stok terbaru sebelum checkout."}
