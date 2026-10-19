from __future__ import annotations

from decimal import Decimal
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
    postal_code: str | None = Field(default=None, max_length=12)

    model_config = {"extra": "forbid"}


class CheckoutRequest(BaseModel):
    items: list[dict[str, Any]] | None = Field(default=None, min_length=1, max_length=50)
    shipping_address: ShippingAddress


class PaymentEvidence(BaseModel):
    amount: Decimal = Field(ge=0)
    method: str = Field(default="manual_transfer", pattern=r"^(manual_transfer|provider)$")
    evidence_reference: str = Field(min_length=1, max_length=1000)


class OrderMutation(BaseModel):
    action: str = Field(min_length=1, max_length=40)
    payload: dict[str, Any] = Field(default_factory=dict)


async def phase07_rpc(function_name: str, body: dict[str, Any], token: str) -> Any:
    if function_name not in {"oto_inventory_mutate", "oto_order_mutate", "oto_expire_reservations"}:
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
    items = request.items
    if items is None:
        carts = await supabase_get("shopping_carts", {"select": "id", "customer_user_id": f"eq.{identity['user']['id']}", "limit": "1"}, identity["_access_token"])
        if not carts:
            raise HTTPException(status_code=422, detail="Keranjang masih kosong.")
        cart_rows = await supabase_get("shopping_cart_items", {"select": "product_id,quantity", "cart_id": f"eq.{carts[0]['id']}", "limit": "50"}, identity["_access_token"])
        items = cart_rows
    normalized: list[dict[str, Any]] = []
    for item in items:
        try:
            normalized.append({"product_id": str(UUID(str(item["product_id"]))), "quantity": int(item["quantity"])})
        except (KeyError, ValueError, TypeError):
            raise HTTPException(status_code=422, detail="Item checkout tidak valid.")
    if not normalized:
        raise HTTPException(status_code=422, detail="Keranjang masih kosong.")
    result = await order_rpc("checkout", None, {
        "items": normalized,
        "shipping_address": request.shipping_address.model_dump(mode="json", exclude_none=True),
        "shipping_fee": "0",
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
        {"select": "id,status,subtotal,shipping_fee,total_amount,currency,tracking_code,shipped_at,delivered_at,created_at,updated_at",
         "customer_user_id": f"eq.{identity['user']['id']}", "order": "created_at.desc", "limit": str(limit), "offset": str(offset)},
        identity["_access_token"],
    )
    return {"items": rows, "count": len(rows), "limit": limit, "offset": offset, "next_offset": offset + limit if len(rows) == limit else None}


@router.get("/v1/orders/{order_id}", tags=["orders"])
async def get_order(order_id: UUID, identity: dict[str, Any] = Depends(require_active_profile)) -> dict[str, Any]:
    rows = await supabase_get(
        "oto_orders",
        {"select": "id,customer_user_id,status,subtotal,shipping_fee,total_amount,currency,shipping_address,tracking_code,shipped_at,delivered_at,cancelled_at,created_at,updated_at",
         "id": f"eq.{order_id}", "limit": "1"},
        identity["_access_token"],
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan.")
    order = rows[0]
    items = await supabase_get("oto_order_items", {"select": "id,product_id,sku_snapshot,name_snapshot,condition_snapshot,unit_price,quantity,line_total", "order_id": f"eq.{order_id}", "limit": "100"}, identity["_access_token"])
    payments = await supabase_get("oto_payment_events", {"select": "id,event_type,amount,method,provider_reference,status,review_note,reviewed_at,created_at", "order_id": f"eq.{order_id}", "order": "created_at.desc", "limit": "50"}, identity["_access_token"])
    returns = await supabase_get("oto_returns", {"select": "id,status,reason,requested_refund,refund_provider_reference,review_note,created_at,updated_at", "order_id": f"eq.{order_id}", "limit": "10"}, identity["_access_token"])
    return {"order": order, "items": items, "payments": payments, "returns": returns}


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
    params = {"select": "id,customer_user_id,status,subtotal,shipping_fee,total_amount,currency,tracking_code,created_at,updated_at",
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
