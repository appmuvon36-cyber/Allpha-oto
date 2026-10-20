from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.main import (
    get_current_identity,
    require_active_profile,
    settings,
    supabase_get,
)

router = APIRouter()


class PaymentIntentRequest(BaseModel):
    provider: str = Field(default="midtrans", pattern=r"^midtrans$")

    model_config = {"extra": "forbid"}


def _midtrans_base() -> str:
    if settings.midtrans_environment == "sandbox":
        return "https://app.sandbox.midtrans.com"
    if settings.midtrans_environment == "production":
        return "https://app.midtrans.com"
    raise HTTPException(status_code=503, detail="Midtrans environment must be sandbox or production.")


def _provider_ready() -> None:
    if not settings.midtrans_server_key:
        raise HTTPException(status_code=503, detail="Online payment is not enabled: Midtrans server credentials are not configured.")


def _webhook_ready() -> None:
    _provider_ready()
    if not settings.supabase_service_role_key:
        raise HTTPException(status_code=503, detail="Payment webhook processing is not enabled: server-side database credential is not configured.")


@router.post("/v1/orders/{order_id}/payment-intent", tags=["payments"])
async def create_payment_intent(
    order_id: UUID,
    request: PaymentIntentRequest = Body(default=PaymentIntentRequest()),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    identity: dict[str, Any] = Depends(require_active_profile),
) -> dict[str, Any]:
    if identity.get("role") != "customer":
        raise HTTPException(status_code=403, detail="Payment intents require an active customer account.")
    _provider_ready()
    if not settings.midtrans_client_key:
        raise HTTPException(status_code=503, detail="Online payment is not enabled: Midtrans client key is not configured.")

    token = identity["_access_token"]
    orders = await supabase_get(
        "oto_orders",
        {"select": "id,customer_user_id,status,total_amount,currency,shipping_address,created_at",
         "id": f"eq.{order_id}", "limit": "1"},
        token,
    )
    if not orders or orders[0].get("customer_user_id") != identity["user"]["id"]:
        raise HTTPException(status_code=404, detail="Order was not found.")
    order = orders[0]
    if order.get("status") != "pending_payment":
        raise HTTPException(status_code=409, detail="Only orders awaiting payment can create a payment intent.")
    try:
        amount = Decimal(str(order["total_amount"]))
    except (KeyError, InvalidOperation):
        raise HTTPException(status_code=409, detail="Order total is invalid.")
    if amount <= 0 or amount != amount.to_integral_value():
        raise HTTPException(status_code=422, detail="Midtrans IDR payment requires a positive whole-rupiah order total.")

    existing = await supabase_get(
        "oto_payment_intents",
        {"select": "id,provider_order_id,amount,status,redirect_url,token,expires_at",
         "order_id": f"eq.{order_id}", "provider": "eq.midtrans",
         "status": "in.(pending,challenge)", "order": "created_at.desc", "limit": "1"},
        token,
    )
    if existing:
        return {"intent": existing[0], "replayed": True}

    provider_order_id = f"oto-{order_id.hex[:24]}-{hashlib.sha256(idempotency_key.encode()).hexdigest()[:10]}"
    address = order.get("shipping_address") if isinstance(order.get("shipping_address"), dict) else {}
    customer_details = {
        "first_name": str(address.get("recipient_name") or "Pelanggan OtoClinic")[:50],
        "phone": str(address.get("phone") or "")[:20],
    }
    item_rows = await supabase_get(
        "oto_order_items",
        {"select": "sku_snapshot,name_snapshot,quantity,unit_price,line_total",
         "order_id": f"eq.{order_id}", "order": "created_at.asc", "limit": "50"},
        token,
    )
    item_details = [
        {"id": str(item.get("sku_snapshot") or f"item-{i+1}")[:50],
         "name": str(item.get("name_snapshot") or "Suku cadang")[:50],
         "quantity": int(item["quantity"]),
         "price": int(Decimal(str(item["unit_price"]))),
        } for i, item in enumerate(item_rows)
    ]
    shipping_fee = Decimal(str(order.get("shipping_fee") or 0))
    if shipping_fee > 0:
        item_details.append({"id": "shipping", "name": "Ongkos kirim", "quantity": 1, "price": int(shipping_fee)})
    if sum(int(x["price"]) * int(x["quantity"]) for x in item_details) != int(amount):
        raise HTTPException(status_code=409, detail="Order item and shipping snapshots do not match the total; payment intent was not created.")
    payload: dict[str, Any] = {
        "transaction_details": {"order_id": provider_order_id, "gross_amount": int(amount)},
        "customer_details": customer_details,
        "item_details": item_details,
        "expiry": {"unit": "minute", "duration": 30},
    }
    if not payload["item_details"]:
        raise HTTPException(status_code=409, detail="Order items are unavailable; payment intent was not created.")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                _midtrans_base() + "/snap/v1/transactions",
                auth=(settings.midtrans_server_key, ""),
                json=payload,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
        if response.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail="Payment provider could not create a transaction.")
        provider_result = response.json()
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Payment provider is temporarily unavailable.") from exc

    if not provider_result.get("token") or not provider_result.get("redirect_url"):
        raise HTTPException(status_code=502, detail="Payment provider returned an incomplete transaction response.")
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    rpc_body = {
        "p_order_id": str(order_id),
        "p_provider": "midtrans",
        "p_provider_order_id": provider_order_id,
        "p_amount": str(amount),
        "p_redirect_url": provider_result["redirect_url"],
        "p_token": provider_result["token"],
        "p_expires_at": expires_at,
    }
    url = settings.supabase_url.rstrip("/")
    headers = {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(f"{url}/rest/v1/rpc/oto_payment_intent_create", headers=headers, json=rpc_body)
        if response.status_code not in (200, 201):
            raise HTTPException(status_code=503, detail="Provider transaction exists but could not be persisted; contact support before retrying.")
        result = response.json()
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Payment intent could not be persisted.") from exc
    return {"intent": result.get("intent", result), "replayed": bool(result.get("replayed", False)), "provider": "midtrans", "client_key": settings.midtrans_client_key, "environment": settings.midtrans_environment}


@router.post("/v1/webhooks/midtrans", tags=["payment-webhooks"])
async def midtrans_webhook(request: Request) -> dict[str, Any]:
    _webhook_ready()
    try:
        payload = await request.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook JSON.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid webhook payload.")
    required = ("order_id", "status_code", "gross_amount", "signature_key", "transaction_status")
    if any(not isinstance(payload.get(key), str) or not payload[key] for key in required):
        raise HTTPException(status_code=400, detail="Required provider notification fields are missing.")
    expected = hashlib.sha512(
        (payload["order_id"] + payload["status_code"] + payload["gross_amount"] + settings.midtrans_server_key).encode()
    ).hexdigest()
    if not hmac.compare_digest(expected, payload["signature_key"]):
        raise HTTPException(status_code=401, detail="Invalid payment notification signature.")

    try:
        amount = Decimal(payload["gross_amount"])
        status_code = payload["transaction_status"]
        if status_code not in {"pending", "capture", "settlement", "deny", "cancel", "expire", "failure", "refund", "partial_refund"}:
            raise ValueError("unsupported status")
        if status_code == "capture" and payload.get("fraud_status") == "challenge":
            status_code = "challenge"
        elif status_code == "capture" and payload.get("fraud_status") not in (None, "accept"):
            status_code = "deny"
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Payment notification values are invalid.") from exc

    transaction_id = str(payload.get("transaction_id") or "")
    event_key = f"{transaction_id or payload['order_id']}:{status_code}:{payload['status_code']}"
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    rpc_body = {
        "p_event_key": event_key,
        "p_provider_order_id": payload["order_id"],
        "p_transaction_id": transaction_id or None,
        "p_status": status_code,
        "p_amount": str(amount),
        "p_payload_digest": digest,
    }
    url = settings.supabase_url.rstrip("/")
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(f"{url}/rest/v1/rpc/oto_payment_webhook_apply", headers=headers, json=rpc_body)
        if response.status_code not in (200, 201):
            raise HTTPException(status_code=503, detail="Payment notification could not be applied; provider will retry.")
        return {"received": True, "result": response.json()}
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Payment notification processing is temporarily unavailable.") from exc
