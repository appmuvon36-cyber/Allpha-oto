from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import re
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.main import require_active_profile, settings, supabase_get

router = APIRouter()
PROVIDER = "rajaongkir"
PENDING_STATUSES = {"PENDING", "pending", "pending_payment", "waiting", "unpaid"}
PAID_STATUSES = {"PAID", "paid", "settlement", "capture", "success", "SUCCESS"}
EXPIRED_STATUSES = {"EXPIRED", "expired", "expire"}
FAILED_STATUSES = {"FAILED", "failed", "deny", "cancel", "cancelled", "canceled", "failure", "rejected"}


class PaymentIntentRequest(BaseModel):
    payment_type: str = Field(pattern=r"^(bank_transfer|qris)$")
    channel_code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    model_config = {"extra": "forbid"}


def _payment_base() -> str:
    env = settings.rajaongkir_payment_environment.strip().lower()
    if env == "sandbox":
        return "https://api-sandbox.collaborator.komerce.id/user"
    if env == "production":
        return "https://api.collaborator.komerce.id/user"
    raise HTTPException(status_code=503, detail="RajaOngkir payment environment must be sandbox or production.")


def _provider_ready() -> None:
    if not settings.rajaongkir_payment_api_key:
        raise HTTPException(status_code=503, detail="RajaOngkir Payment API is not enabled; configure its API key in Railway.")


def _callback_ready() -> None:
    if not settings.rajaongkir_payment_callback_secret:
        raise HTTPException(status_code=503, detail="Payment callbacks are disabled until the callback secret is configured.")


def _headers() -> dict[str, str]:
    return {"x-api-key": settings.rajaongkir_payment_api_key, "Accept": "application/json", "Content-Type": "application/json"}


def _unwrap(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    for key in ("data", "result", "payment", "transaction"):
        value = payload.get(key)
        if isinstance(value, dict):
            merged = dict(payload)
            merged.update(value)
            return merged
    return payload


def _field(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def _normalized_status(value: Any) -> str:
    status = str(value or "").strip()
    if status in PAID_STATUSES:
        return "paid"
    if status in EXPIRED_STATUSES:
        return "expired"
    if status in FAILED_STATUSES:
        return "failed"
    if status in PENDING_STATUSES:
        return "pending"
    raise HTTPException(status_code=422, detail="RajaOngkir returned an unsupported payment status.")


async def _provider_json(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    _provider_ready()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.request(method, url, headers=_headers(), **kwargs)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="RajaOngkir Payment API is temporarily unavailable.") from exc
    if response.status_code == 401 or response.status_code == 403:
        raise HTTPException(status_code=503, detail="RajaOngkir Payment API rejected the server credentials.")
    if response.status_code == 429 or response.status_code >= 500:
        raise HTTPException(status_code=503, detail="RajaOngkir Payment API is temporarily unavailable.")
    if response.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail="RajaOngkir Payment API rejected the request.")
    try:
        result = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="RajaOngkir Payment API returned an invalid response.") from exc
    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail="RajaOngkir Payment API returned an unexpected response.")
    if result.get("success") is False or result.get("status") in ("error", "failed"):
        raise HTTPException(status_code=502, detail="RajaOngkir Payment API could not process the request.")
    return result


@router.get("/v1/payments/methods", tags=["payments"])
async def get_payment_methods(identity: dict[str, Any] = Depends(require_active_profile)) -> dict[str, Any]:
    if identity.get("role") != "customer":
        raise HTTPException(status_code=403, detail="Payment methods require an active customer account.")
    result = await _provider_json("GET", _payment_base() + "/api/v1/user/methods")
    return {"provider": PROVIDER, "environment": settings.rajaongkir_payment_environment, "methods": result.get("data", result)}


@router.post("/v1/orders/{order_id}/payment-intent", tags=["payments"])
async def create_payment_intent(
    order_id: UUID,
    request: PaymentIntentRequest = Body(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    identity: dict[str, Any] = Depends(require_active_profile),
) -> dict[str, Any]:
    if identity.get("role") != "customer":
        raise HTTPException(status_code=403, detail="Payment intents require an active customer account.")
    _provider_ready()
    token = identity["_access_token"]
    orders = await supabase_get("oto_orders", {
        "select": "id,customer_user_id,status,total_amount,shipping_address,created_at",
        "id": f"eq.{order_id}", "limit": "1"
    }, token)
    if not orders or orders[0].get("customer_user_id") != identity["user"]["id"]:
        raise HTTPException(status_code=404, detail="Order was not found.")
    order = orders[0]
    if order.get("status") != "pending_payment":
        raise HTTPException(status_code=409, detail="Only orders awaiting payment can create a payment intent.")
    try:
        amount = Decimal(str(order["total_amount"]))
    except (KeyError, InvalidOperation):
        raise HTTPException(status_code=409, detail="Order total is invalid.")
    if amount <= 0 or amount != amount.to_integral_value() or amount < 10000:
        raise HTTPException(status_code=422, detail="RajaOngkir Payment API requires a whole-IDR amount of at least Rp10.000.")

    existing = await supabase_get("oto_payment_intents", {
        "select": "id,provider_order_id,provider_transaction_id,amount,status,redirect_url,token,expires_at",
        "order_id": f"eq.{order_id}", "provider": "eq.rajaongkir",
        "status": "eq.pending", "order": "created_at.desc", "limit": "1"
    }, token)
    if existing:
        return {"intent": existing[0], "replayed": True, "provider": PROVIDER}

    provider_order_id = f"oto-{order_id.hex}-{hashlib.sha256(idempotency_key.encode()).hexdigest()[:10]}"
    address = order.get("shipping_address") if isinstance(order.get("shipping_address"), dict) else {}
    customer_name = str(address.get("recipient_name") or identity.get("profile", {}).get("display_name") or "Pelanggan OtoClinic")[:100]
    customer_phone = str(address.get("phone") or identity.get("profile", {}).get("phone") or "")[:40]
    customer_email = str(identity.get("user", {}).get("email") or "")
    if not customer_phone or not customer_email:
        raise HTTPException(status_code=422, detail="Lengkapi email akun dan nomor telepon penerima sebelum membayar.")
    item_rows = await supabase_get("oto_order_items", {
        "select": "sku_snapshot,name_snapshot,quantity,unit_price,line_total",
        "order_id": f"eq.{order_id}", "limit": "50"
    }, token)
    item_details = []
    for item in item_rows:
        try:
            quantity = int(item["quantity"])
            price = Decimal(str(item["unit_price"]))
        except (KeyError, ValueError, InvalidOperation):
            raise HTTPException(status_code=409, detail="Order item snapshot is invalid.")
        if quantity < 1 or price < 0 or price != price.to_integral_value():
            raise HTTPException(status_code=409, detail="Order item price or quantity is invalid.")
        item_details.append({"name": str(item.get("name_snapshot") or "Suku cadang")[:180], "quantity": quantity, "price": int(price)})
    if not item_details or sum(item["quantity"] * item["price"] for item in item_details) > int(amount):
        raise HTTPException(status_code=409, detail="Order item snapshots do not match the order total.")
    payload = {
        "order_id": provider_order_id,
        "payment_type": request.payment_type,
        "channel_code": request.channel_code,
        "amount": int(amount),
        "customer": {"name": customer_name, "email": customer_email, "phone": customer_phone},
        "items": item_details,
        "expiry_duration": 3600,
        "callback_url": settings.rajaongkir_payment_callback_url,
        "callback_api_key": settings.rajaongkir_payment_callback_secret,
    }
    if not payload["callback_url"] or not settings.rajaongkir_payment_callback_secret:
        raise HTTPException(status_code=503, detail="Payment callback URL and callback secret must be configured before payment activation.")
    provider_raw = await _provider_json("POST", _payment_base() + "/api/v1/user/payment/create", json=payload)
    provider_result = _unwrap(provider_raw)
    payment_id = _field(provider_result, "payment_id", "id", "transaction_id", "reference_id")
    if payment_id is None:
        raise HTTPException(status_code=502, detail="RajaOngkir response did not include a payment identifier.")
    payment_id = str(payment_id)
    if len(payment_id) > 180:
        raise HTTPException(status_code=502, detail="RajaOngkir payment identifier has an unexpected length.")
    payment_url = _field(provider_result, "payment_url", "checkout_url", "redirect_url", "url")
    va_number = _field(provider_result, "va_number", "account_number", "virtual_account_number")
    qr_value = _field(provider_result, "qr_string", "qr_code", "qr_content", "qr_url")
    expires_raw = _field(provider_result, "expired_at", "expires_at", "expiry_time")
    expires_at = None
    if expires_raw:
        try:
            expires_at = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
        except ValueError:
            expires_at = None
    if expires_at is None:
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=3600)).isoformat()
    # Persist provider payment ID in token and response metadata without leaking credentials.
    rpc_body = {
        "p_order_id": str(order_id), "p_provider": PROVIDER, "p_provider_order_id": provider_order_id,
        "p_amount": str(amount), "p_redirect_url": str(payment_url) if payment_url else None,
        "p_token": payment_id, "p_expires_at": expires_at
    }
    url = settings.supabase_url.rstrip("/")
    headers = {"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            saved = await client.post(f"{url}/rest/v1/rpc/oto_payment_intent_create", headers=headers, json=rpc_body)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Payment intent could not be persisted.") from exc
    if saved.status_code not in (200, 201):
        raise HTTPException(status_code=503, detail="Provider transaction exists but could not be safely recorded; contact support before retrying.")
    try:
        saved_data = saved.json()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="Payment intent persistence returned an invalid response.") from exc
    intent = saved_data.get("intent", saved_data) if isinstance(saved_data, dict) else {}
    return {
        "provider": PROVIDER, "environment": settings.rajaongkir_payment_environment,
        "intent": intent, "replayed": bool(saved_data.get("replayed", False)) if isinstance(saved_data, dict) else False,
        "payment": {"payment_id": payment_id, "payment_type": request.payment_type, "channel_code": request.channel_code,
                    "payment_url": payment_url, "va_number": va_number, "qr_value": qr_value,
                    "expires_at": expires_at, "raw_status": _field(provider_result, "status", "payment_status")}
    }


@router.get("/v1/orders/{order_id}/payment-status", tags=["payments"])
async def reconcile_payment_status(
    order_id: UUID,
    identity: dict[str, Any] = Depends(require_active_profile),
) -> dict[str, Any]:
    if identity.get("role") != "customer":
        raise HTTPException(status_code=403, detail="Payment status requires an active customer account.")
    _provider_ready()
    token = identity["_access_token"]
    orders = await supabase_get("oto_orders", {"select": "id,customer_user_id,status,total_amount", "id": f"eq.{order_id}", "limit": "1"}, token)
    if not orders or orders[0].get("customer_user_id") != identity["user"]["id"]:
        raise HTTPException(status_code=404, detail="Order was not found.")
    intents = await supabase_get("oto_payment_intents", {
        "select": "id,provider_order_id,provider_transaction_id,amount,status,token,created_at",
        "order_id": f"eq.{order_id}", "provider": "eq.rajaongkir", "order": "created_at.desc", "limit": "1"
    }, token)
    if not intents:
        raise HTTPException(status_code=404, detail="No RajaOngkir payment intent exists for this order.")
    intent = intents[0]
    payment_id = intent.get("token") or intent.get("provider_transaction_id")
    if not payment_id:
        raise HTTPException(status_code=409, detail="Payment intent is missing its provider payment ID.")
    raw = await _provider_json("GET", _payment_base() + "/api/v1/user/payment/status/" + str(payment_id))
    result = _unwrap(raw)
    status = _normalized_status(_field(result, "status", "payment_status", "transaction_status"))
    amount_raw = _field(result, "amount", "gross_amount", "total_amount")
    if amount_raw is not None:
        try:
            if Decimal(str(amount_raw)) != Decimal(str(intent["amount"])):
                raise HTTPException(status_code=409, detail="RajaOngkir status amount does not match the order.")
        except InvalidOperation as exc:
            raise HTTPException(status_code=502, detail="RajaOngkir returned an invalid amount.") from exc
    if status == "paid":
        await _apply_verified_status("status:" + str(payment_id) + ":paid", intent["provider_order_id"], str(payment_id), "paid", Decimal(str(intent["amount"])), hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest())
    return {"provider": PROVIDER, "payment_id": str(payment_id), "status": status, "order_status": orders[0].get("status"), "provider_response": {k: result[k] for k in ("status", "payment_status", "expired_at", "va_number", "payment_type") if k in result}}


async def _apply_verified_status(event_key: str, provider_order_id: str, transaction_id: str | None, status: str, amount: Decimal | None, digest: str) -> dict[str, Any]:
    if not settings.supabase_service_role_key:
        raise HTTPException(status_code=503, detail="Server-side payment reconciliation is not configured.")
    url = settings.supabase_url.rstrip("/")
    headers = {"apikey": settings.supabase_service_role_key, "Authorization": f"Bearer {settings.supabase_service_role_key}", "Content-Type": "application/json"}
    body = {"p_event_key": event_key[:200], "p_provider": PROVIDER, "p_provider_order_id": provider_order_id,
            "p_transaction_id": transaction_id, "p_status": status, "p_amount": str(amount) if amount is not None else None, "p_payload_digest": digest}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(f"{url}/rest/v1/rpc/oto_payment_webhook_apply", headers=headers, json=body)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Payment reconciliation could not be persisted.") from exc
    if response.status_code not in (200, 201):
        raise HTTPException(status_code=503, detail="Payment reconciliation was not accepted by the database.")
    try:
        result = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="Payment reconciliation returned an invalid response.") from exc
    return result if isinstance(result, dict) else {}


@router.post("/v1/webhooks/rajaongkir", tags=["payment-webhooks"])
async def rajaongkir_webhook(request: Request) -> dict[str, Any]:
    _callback_ready()
    raw_body = await request.body()
    supplied = request.headers.get("X-Callback-Api-Key", "").strip()
    expected = hmac.new(settings.rajaongkir_payment_callback_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=401, detail="Invalid RajaOngkir callback signature.")
    try:
        parsed = json.loads(raw_body)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid callback JSON.") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="Invalid callback payload.")
    data = _unwrap(parsed)
    provider_order_id = _field(data, "order_id", "merchant_order_id", "external_id")
    payment_id = _field(data, "payment_id", "id", "transaction_id", "reference_id")
    raw_status = _field(data, "status", "payment_status", "transaction_status")
    amount_raw = _field(data, "amount", "gross_amount", "total_amount")
    if not provider_order_id or not raw_status:
        raise HTTPException(status_code=422, detail="Callback is missing order_id or payment status.")
    status = _normalized_status(raw_status)
    amount = None
    if amount_raw is not None:
        try:
            amount = Decimal(str(amount_raw))
        except InvalidOperation as exc:
            raise HTTPException(status_code=422, detail="Callback amount is invalid.") from exc
    if status == "paid" and amount is None:
        raise HTTPException(status_code=422, detail="Paid callback must include an amount.")
    digest = hashlib.sha256(raw_body).hexdigest()
    event_key = str(_field(data, "event_id", "callback_id", "payment_id", "id") or f"{provider_order_id}:{status}:{digest[:24]}")
    await _apply_verified_status(event_key, str(provider_order_id), str(payment_id) if payment_id else None, status, amount, digest)
    return {"received": True}


__all__ = ["router"]
