from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import re
from typing import Any
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.main import require_active_profile, require_roles, require_supabase_configuration, settings
from app.payments import _apply_verified_status, _field, _normalized_status, _payment_base, _provider_json, _unwrap

router = APIRouter()
CONSENT_VERSION = "whatsapp-order-status-v1"
_ALLOWED_SERVICE_RPCS = {
    "oto_integration_outbox_enqueue",
    "oto_integration_outbox_claim",
    "oto_integration_outbox_complete",
    "oto_integration_outbox_fail",
    "oto_integration_outbox_requeue",
}


class WhatsAppConsentRequest(BaseModel):
    opt_in: bool
    consent_version: str | None = Field(default=None, max_length=80)
    model_config = {"extra": "forbid"}


class OutboxEnqueueResult(BaseModel):
    id: str
    event_key: str
    status: str
    correlation_id: str
    attempt_count: int
    replayed: bool = False


class IntegrationProviderError(Exception):
    def __init__(self, code: str, retryable: bool):
        super().__init__(code)
        self.code = code
        self.retryable = retryable


def _correlation_id(request: Request) -> str:
    supplied = request.headers.get("X-Request-ID", "").strip()
    if supplied and re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", supplied):
        return supplied
    return str(uuid4())


def _service_credentials() -> tuple[str, str]:
    url = settings.supabase_url.rstrip("/")
    key = settings.supabase_service_role_key.strip()
    if not url or not key:
        raise HTTPException(status_code=503, detail="Server-side integration storage is not configured.")
    return url, key


async def _service_get(table: str, params: dict[str, str]) -> list[dict[str, Any]]:
    url, key = _service_credentials()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{url}/rest/v1/{table}", params=params,
                headers={"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Integration storage is temporarily unavailable.") from exc
    if response.status_code in (429,) or response.status_code >= 500:
        raise HTTPException(status_code=503, detail="Integration storage is temporarily unavailable.")
    if response.status_code != 200:
        raise HTTPException(status_code=503, detail="Integration storage read was not permitted.")
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="Integration storage returned an invalid response.") from exc
    if not isinstance(data, list):
        raise HTTPException(status_code=503, detail="Integration storage returned an unexpected response.")
    return data


async def _service_write(table: str, method: str, body: dict[str, Any], params: dict[str, str] | None = None) -> list[dict[str, Any]]:
    url, key = _service_credentials()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.request(
                method, f"{url}/rest/v1/{table}", params=params, json=body,
                headers={"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json",
                         "Content-Type": "application/json", "Prefer": "return=representation"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Integration storage write is temporarily unavailable.") from exc
    if response.status_code == 429 or response.status_code >= 500:
        raise HTTPException(status_code=503, detail="Integration storage write is temporarily unavailable.")
    if response.status_code not in (200, 201, 204):
        raise HTTPException(status_code=503, detail="Integration storage write was not accepted.")
    if response.status_code == 204 or not response.content:
        return []
    try:
        data = response.json()
    except ValueError:
        return []
    return data if isinstance(data, list) else [data] if isinstance(data, dict) else []


async def _service_rpc(name: str, body: dict[str, Any]) -> Any:
    if name not in _ALLOWED_SERVICE_RPCS:
        raise HTTPException(status_code=422, detail="Unsupported integration operation.")
    url, key = _service_credentials()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{url}/rest/v1/rpc/{name}", json=body,
                headers={"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json", "Content-Type": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Integration operation timed out or could not reach the database.") from exc
    if response.status_code == 429 or response.status_code >= 500:
        raise HTTPException(status_code=503, detail="Integration operation is temporarily unavailable.")
    if response.status_code not in (200, 201):
        try:
            error = response.json()
            code = str(error.get("code", ""))
            message = str(error.get("message", ""))
        except (ValueError, AttributeError):
            code, message = "", ""
        if code == "P0002" or "not_found" in message:
            raise HTTPException(status_code=404, detail="Integration record was not found.")
        if code == "22023" or code == "23505" or code == "40001":
            raise HTTPException(status_code=409, detail="Integration state changed or the request conflicts with an earlier action.")
        raise HTTPException(status_code=503, detail="Integration operation was not accepted by the database.")
    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="Integration operation returned an invalid response.") from exc


async def _caller_rpc(name: str, body: dict[str, Any], identity: dict[str, Any]) -> Any:
    if name != "oto_whatsapp_consent_set":
        raise HTTPException(status_code=422, detail="Unsupported customer preference operation.")
    url, anon_key = require_supabase_configuration()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{url}/rest/v1/rpc/{name}", json=body,
                headers={"apikey": anon_key, "Authorization": f"Bearer {identity['_access_token']}",
                         "Accept": "application/json", "Content-Type": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Notification preference could not be saved.") from exc
    if response.status_code in (401, 403):
        raise HTTPException(status_code=403, detail="Notification preference change is not permitted.")
    if response.status_code == 429 or response.status_code >= 500:
        raise HTTPException(status_code=503, detail="Notification preference service is temporarily unavailable.")
    if response.status_code not in (200, 201):
        try:
            error = response.json()
            code = str(error.get("code", ""))
        except (ValueError, AttributeError):
            code = ""
        if code == "22023":
            raise HTTPException(status_code=422, detail="Notification consent details are invalid.")
        raise HTTPException(status_code=403, detail="Notification preference change is not permitted.")
    return response.json()


def _provider_readiness() -> dict[str, Any]:
    payment = bool(settings.rajaongkir_payment_api_key.strip() and settings.rajaongkir_payment_callback_secret.strip()
                   and settings.rajaongkir_payment_callback_url.strip() and settings.supabase_service_role_key.strip())
    shipping = bool(settings.rajaongkir_api_key.strip() and settings.rajaongkir_quote_signing_secret.strip())
    whatsapp = bool(settings.whatsapp_cloud_api_token.strip() and settings.whatsapp_phone_number_id.strip()
                     and settings.whatsapp_graph_api_version.strip() and settings.whatsapp_order_status_template.strip()
                     and settings.supabase_service_role_key.strip())
    return {
        "providers": {
            "rajaongkir_payment": {"configured": payment, "mode": settings.rajaongkir_payment_environment if payment else "disabled"},
            "rajaongkir_shipping": {"configured": shipping, "mode": "live" if shipping else "disabled"},
            "whatsapp_cloud": {"configured": whatsapp, "mode": "live" if whatsapp else "disabled"},
        },
        "worker": {"internal_secret_configured": bool(settings.integration_worker_secret.strip())},
        "capabilities": {
            "webhook_signature_validation": bool(settings.rajaongkir_payment_callback_secret.strip()),
            "payment_reconciliation": payment,
            "outbox_retry": True,
            "dead_letter_requeue": True,
            "whatsapp_consent_required": True,
        },
    }


def _normalize_indonesian_phone(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    elif digits.startswith("8"):
        digits = "62" + digits
    if not re.fullmatch(r"[1-9][0-9]{7,14}", digits):
        raise HTTPException(status_code=422, detail="Nomor WhatsApp pelanggan belum valid.")
    return digits


async def _send_whatsapp_template(payload: dict[str, Any]) -> tuple[str | None, str]:
    if not (settings.whatsapp_cloud_api_token.strip() and settings.whatsapp_phone_number_id.strip()
            and settings.whatsapp_graph_api_version.strip()):
        raise IntegrationProviderError("whatsapp_provider_not_configured", True)
    to = str(payload.get("to") or "")
    template_name = str(payload.get("template_name") or "")
    language = str(payload.get("language_code") or "id")
    parameters = payload.get("parameters")
    if not re.fullmatch(r"[1-9][0-9]{7,14}", to) or not re.fullmatch(r"[a-z0-9_]{2,120}", template_name):
        raise IntegrationProviderError("whatsapp_payload_invalid", False)
    if not isinstance(parameters, list) or len(parameters) > 10 or any(not isinstance(x, str) or len(x) > 512 for x in parameters):
        raise IntegrationProviderError("whatsapp_template_parameters_invalid", False)
    body = {
        "messaging_product": "whatsapp", "recipient_type": "individual", "to": to, "type": "template",
        "template": {"name": template_name, "language": {"code": language},
                     "components": [{"type": "body", "parameters": [{"type": "text", "text": x} for x in parameters]}] if parameters else []},
    }
    version = settings.whatsapp_graph_api_version.strip()
    if not re.fullmatch(r"v[0-9]{1,3}\.[0-9]{1,2}", version):
        raise IntegrationProviderError("whatsapp_graph_version_invalid", False)
    url = f"https://graph.facebook.com/{version}/{settings.whatsapp_phone_number_id.strip()}/messages"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=body, headers={"Authorization": "Bearer " + settings.whatsapp_cloud_api_token.strip(), "Content-Type": "application/json"})
    except httpx.TimeoutException as exc:
        raise IntegrationProviderError("whatsapp_timeout", True) from exc
    except httpx.HTTPError as exc:
        raise IntegrationProviderError("whatsapp_network_error", True) from exc
    digest = hashlib.sha256(response.content).hexdigest()
    if response.status_code == 429 or response.status_code >= 500:
        raise IntegrationProviderError("whatsapp_provider_transient", True)
    try:
        result = response.json()
    except ValueError as exc:
        raise IntegrationProviderError("whatsapp_response_invalid", response.status_code >= 500) from exc
    if response.status_code not in (200, 201):
        error = result.get("error", {}) if isinstance(result, dict) else {}
        transient = bool(error.get("is_transient")) or str(error.get("code", "")) in {"130429", "131056", "131057"}
        code = "whatsapp_provider_" + re.sub(r"[^A-Za-z0-9_-]", "", str(error.get("code", "rejected")))[:32]
        raise IntegrationProviderError(code, transient)
    messages = result.get("messages", []) if isinstance(result, dict) else []
    message_id = str(messages[0].get("id"))[:240] if messages and isinstance(messages[0], dict) and messages[0].get("id") else None
    if not message_id:
        raise IntegrationProviderError("whatsapp_message_id_missing", True)
    return message_id, digest


async def _dispatch_batch(limit: int, correlation_id: str) -> dict[str, Any]:
    if not _provider_readiness()["providers"]["whatsapp_cloud"]["configured"]:
        raise HTTPException(status_code=503, detail="WhatsApp Cloud API belum dikonfigurasi; antrean tetap tersimpan dan tidak diproses.")
    claimed = await _service_rpc("oto_integration_outbox_claim", {"p_limit": limit, "p_lease_seconds": 90})
    if isinstance(claimed, dict):
        rows = claimed.get("items", [])
    else:
        rows = claimed
    if not isinstance(rows, list):
        raise HTTPException(status_code=503, detail="Outbox claim returned an invalid response.")
    completed = retried = dead_letter = 0
    results: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_id = str(row.get("id") or "")
        lock_token = str(row.get("lock_token") or "")
        row_correlation = str(row.get("correlation_id") or correlation_id)
        try:
            if row.get("provider") != "whatsapp_cloud" or row.get("event_type") != "whatsapp_template":
                raise IntegrationProviderError("unsupported_outbox_event", False)
            payload = row.get("payload")
            if not isinstance(payload, dict):
                raise IntegrationProviderError("outbox_payload_invalid", False)
            message_id, response_digest = await _send_whatsapp_template(payload)
            await _service_rpc("oto_integration_outbox_complete", {
                "p_id": row_id, "p_lock_token": lock_token,
                "p_provider_message_id": message_id, "p_response_digest": response_digest,
            })
            completed += 1
            results.append({"id": row_id, "status": "delivered", "correlation_id": row_correlation})
        except IntegrationProviderError as exc:
            try:
                result = await _service_rpc("oto_integration_outbox_fail", {
                    "p_id": row_id, "p_lock_token": lock_token, "p_error_code": exc.code, "p_retryable": exc.retryable,
                })
                status = result.get("status", "retry") if isinstance(result, dict) else "retry"
                retried += int(status == "retry")
                dead_letter += int(status == "dead_letter")
                results.append({"id": row_id, "status": status, "error_code": exc.code, "correlation_id": row_correlation})
            except HTTPException:
                results.append({"id": row_id, "status": "lease_lost", "correlation_id": row_correlation})
        except HTTPException:
            # Do not turn database failures into successful deliveries. Leave the lease to expire,
            # allowing the claim worker to recover the record without acknowledging it.
            results.append({"id": row_id, "status": "persistence_error", "correlation_id": row_correlation})
    return {"correlation_id": correlation_id, "claimed": len(rows), "delivered": completed, "retry_scheduled": retried,
            "dead_lettered": dead_letter, "items": results}


@router.get("/v1/admin/integrations/status", tags=["integrations"])
async def integration_status(identity: dict[str, Any] = Depends(require_roles("admin", "order_manager"))) -> dict[str, Any]:
    return _provider_readiness()


@router.get("/v1/admin/integrations/outbox", tags=["integrations"])
async def list_integration_outbox(
    status: str | None = Query(default=None, pattern=r"^(pending|processing|retry|delivered|dead_letter)$"),
    provider: str | None = Query(default=None, pattern=r"^whatsapp_cloud$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
    identity: dict[str, Any] = Depends(require_roles("admin", "order_manager")),
) -> dict[str, Any]:
    params = {"select": "id,event_key,provider,event_type,correlation_id,aggregate_type,aggregate_id,status,attempt_count,max_attempts,next_attempt_at,last_error_code,last_error_at,delivered_at,provider_message_id,created_at,updated_at",
              "order": "created_at.desc", "limit": str(limit), "offset": str(offset)}
    if status:
        params["status"] = "eq." + status
    if provider:
        params["provider"] = "eq." + provider
    rows = await _service_get("oto_integration_outbox", params)
    return {"items": rows, "count": len(rows), "limit": limit, "offset": offset,
            "next_offset": offset + limit if len(rows) == limit else None}


@router.get("/v1/admin/integrations/reconciliations", tags=["integrations"])
async def list_integration_reconciliations(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
    identity: dict[str, Any] = Depends(require_roles("admin", "order_manager")),
) -> dict[str, Any]:
    rows = await _service_get("oto_integration_reconciliation_runs", {
        "select": "id,provider,run_type,status,correlation_id,started_at,completed_at,scanned_count,matched_count,mismatch_count,failed_count,summary,created_by,created_at",
        "order": "started_at.desc", "limit": str(limit), "offset": str(offset),
    })
    return {"items": rows, "count": len(rows), "limit": limit, "offset": offset,
            "next_offset": offset + limit if len(rows) == limit else None}


@router.post("/v1/admin/integrations/outbox/{outbox_id}/retry", tags=["integrations"])
async def requeue_integration_outbox(
    outbox_id: UUID,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    identity: dict[str, Any] = Depends(require_roles("admin")),
) -> dict[str, Any]:
    result = await _service_rpc("oto_integration_outbox_requeue", {
        "p_id": str(outbox_id), "p_actor_user_id": str(identity["user"]["id"]), "p_request_id": idempotency_key,
    })
    return {"result": result, "correlation_id": _correlation_id(request)}


@router.post("/v1/admin/integrations/dispatch", tags=["integrations"])
async def admin_dispatch_integrations(
    request: Request,
    limit: int = Query(default=10, ge=1, le=50),
    identity: dict[str, Any] = Depends(require_roles("admin", "order_manager")),
) -> dict[str, Any]:
    return await _dispatch_batch(limit, _correlation_id(request))


@router.post("/v1/internal/integrations/dispatch", tags=["integrations"])
async def internal_dispatch_integrations(
    request: Request,
    limit: int = Query(default=10, ge=1, le=50),
    worker_secret: str = Header(default="", alias="X-Integration-Worker-Secret"),
) -> dict[str, Any]:
    expected = settings.integration_worker_secret.strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Integration worker secret is not configured.")
    if not worker_secret or not hmac.compare_digest(worker_secret, expected):
        raise HTTPException(status_code=401, detail="Integration worker authentication failed.")
    return await _dispatch_batch(limit, _correlation_id(request))


@router.post("/v1/notifications/whatsapp-consent", tags=["notifications"])
async def set_whatsapp_consent(
    request: WhatsAppConsentRequest = Body(...),
    http_request: Request = None,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    identity: dict[str, Any] = Depends(require_active_profile),
) -> dict[str, Any]:
    if identity.get("role") != "customer":
        raise HTTPException(status_code=403, detail="WhatsApp notification preferences require a customer account.")
    if request.opt_in and request.consent_version != CONSENT_VERSION:
        raise HTTPException(status_code=422, detail="Baca dan setujui ketentuan notifikasi WhatsApp yang berlaku.")
    result = await _caller_rpc("oto_whatsapp_consent_set", {
        "p_opt_in": request.opt_in,
        "p_consent_version": request.consent_version if request.opt_in else CONSENT_VERSION,
        "p_request_id": idempotency_key,
    }, identity)
    return {"preference": result, "correlation_id": _correlation_id(http_request) if http_request else str(uuid4())}


@router.get("/v1/notifications/whatsapp-consent", tags=["notifications"])
async def get_whatsapp_consent(identity: dict[str, Any] = Depends(require_active_profile)) -> dict[str, Any]:
    if identity.get("role") != "customer":
        raise HTTPException(status_code=403, detail="WhatsApp notification preferences require a customer account.")
    rows = await _service_get("oto_notification_preferences", {
        "select": "whatsapp_opt_in,consent_version,consented_at,revoked_at,updated_at",
        "customer_user_id": "eq." + str(identity["user"]["id"]), "limit": "1",
    })
    return {"preference": rows[0] if rows else {"whatsapp_opt_in": False, "consent_version": None, "consented_at": None, "revoked_at": None}}


@router.post("/v1/admin/orders/{order_id}/whatsapp-status-notification", tags=["integrations"], status_code=202)
async def enqueue_order_status_whatsapp(
    order_id: UUID,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    identity: dict[str, Any] = Depends(require_roles("admin", "order_manager")),
) -> dict[str, Any]:
    readiness = _provider_readiness()["providers"]["whatsapp_cloud"]
    if not readiness["configured"]:
        raise HTTPException(status_code=503, detail="WhatsApp Cloud API dan template status pesanan belum dikonfigurasi.")
    order_rows = await _service_get("oto_orders", {
        "select": "id,customer_user_id,status,created_at", "id": "eq." + str(order_id), "limit": "1",
    })
    if not order_rows:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan.")
    order = order_rows[0]
    pref = await _service_get("oto_notification_preferences", {
        "select": "whatsapp_opt_in,revoked_at", "customer_user_id": "eq." + str(order["customer_user_id"]), "limit": "1",
    })
    if not pref or pref[0].get("whatsapp_opt_in") is not True or pref[0].get("revoked_at") is not None:
        raise HTTPException(status_code=409, detail="Pelanggan belum memberikan persetujuan aktif untuk notifikasi WhatsApp.")
    profiles = await _service_get("user_profiles", {
        "select": "id,phone,is_active,role", "id": "eq." + str(order["customer_user_id"]), "limit": "1",
    })
    if not profiles or profiles[0].get("is_active") is not True or profiles[0].get("role") != "customer":
        raise HTTPException(status_code=409, detail="Profil pelanggan tidak aktif.")
    to = _normalize_indonesian_phone(profiles[0].get("phone"))
    status = str(order.get("status") or "")
    labels = {"pending_payment":"menunggu pembayaran","payment_review":"bukti pembayaran ditinjau","paid":"pembayaran terverifikasi",
              "processing":"pesanan diproses","shipped":"pesanan dikirim","delivered":"pesanan diterima","cancelled":"pesanan dibatalkan",
              "return_requested":"retur diajukan","returned":"retur selesai","partially_returned":"retur sebagian"}
    if status not in labels:
        raise HTTPException(status_code=409, detail="Status pesanan belum didukung untuk notifikasi.")
    payload = {"to": to, "template_name": settings.whatsapp_order_status_template.strip(),
               "language_code": settings.whatsapp_template_language.strip() or "id",
               "parameters": [str(order_id)[-8:].upper(), labels[status]]}
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    correlation = _correlation_id(request)
    result = await _service_rpc("oto_integration_outbox_enqueue", {
        "p_event_key": f"order-status:{order_id}:{status}",
        "p_provider": "whatsapp_cloud", "p_event_type": "whatsapp_template",
        "p_correlation_id": correlation, "p_aggregate_type": "order", "p_aggregate_id": str(order_id),
        "p_payload": payload, "p_payload_fingerprint": fingerprint,
    })
    return {"outbox": result, "correlation_id": correlation, "message": "Notifikasi dimasukkan ke antrean; ini bukan bukti pesan telah terkirim."}


@router.post("/v1/admin/integrations/reconcile-payments", tags=["integrations"])
async def reconcile_pending_payments(
    request: Request,
    limit: int = Query(default=25, ge=1, le=100),
    identity: dict[str, Any] = Depends(require_roles("admin", "order_manager")),
) -> dict[str, Any]:
    if not _provider_readiness()["providers"]["rajaongkir_payment"]["configured"]:
        raise HTTPException(status_code=503, detail="Rekonsiliasi pembayaran belum dikonfigurasi lengkap.")
    correlation = _correlation_id(request)
    started = datetime.now(timezone.utc).isoformat()
    run_rows = await _service_write("oto_integration_reconciliation_runs", "POST", {
        "provider": "rajaongkir", "run_type": "pending_payment_scan", "status": "running",
        "correlation_id": correlation, "started_at": started, "created_by": identity["user"]["id"],
        "summary": {"mode": "bounded_pending_scan"},
    })
    run_id = str(run_rows[0]["id"]) if run_rows else None
    try:
        intents = await _service_get("oto_payment_intents", {
            "select": "id,order_id,provider_order_id,provider_transaction_id,amount,status,token,created_at",
            "provider": "eq.rajaongkir", "status": "in.(pending,challenge)",
            "order": "created_at.asc", "limit": str(limit),
        })
    except HTTPException:
        if run_id:
            try:
                await _service_write("oto_integration_reconciliation_runs", "PATCH", {
                    "status": "failed", "completed_at": datetime.now(timezone.utc).isoformat(),
                    "summary": {"failure_codes": ["payment_intent_scan_failed"]},
                }, {"id": "eq." + run_id})
            except HTTPException:
                pass
        raise
    matched = mismatched = failed = 0
    safe_failures: list[str] = []
    for intent in intents:
        payment_id = str(intent.get("token") or intent.get("provider_transaction_id") or "")
        if not payment_id:
            failed += 1
            safe_failures.append("payment_id_missing")
            continue
        try:
            raw = await _provider_json("GET", _payment_base() + "/api/v1/user/payment/status/" + quote(payment_id, safe=""))
            data = _unwrap(raw)
            status = _normalized_status(_field(data, "status", "payment_status", "transaction_status"))
            amount_raw = _field(data, "amount", "gross_amount", "total_amount")
            if status == "pending":
                matched += 1
                continue
            if amount_raw is None:
                mismatched += 1
                safe_failures.append("terminal_amount_missing")
                continue
            try:
                amount = Decimal(str(amount_raw))
                expected = Decimal(str(intent["amount"]))
            except (InvalidOperation, KeyError):
                mismatched += 1
                safe_failures.append("amount_invalid")
                continue
            if amount != expected:
                mismatched += 1
                safe_failures.append("amount_mismatch")
                continue
            digest = hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            event_key = f"reconcile:{payment_id}:{status}:{digest[:20]}"
            await _apply_verified_status(event_key, str(intent["provider_order_id"]), payment_id, status, amount, digest)
            matched += 1
        except HTTPException as exc:
            failed += 1
            safe_failures.append("provider_or_persistence_error_" + str(exc.status_code))
        except Exception:
            failed += 1
            safe_failures.append("unexpected_reconciliation_error")
    finished = datetime.now(timezone.utc).isoformat()
    run_status = "completed" if not failed and not mismatched else ("partial" if matched or len(intents) == 0 else "failed")
    summary = {"failure_codes": sorted(set(safe_failures))[:12], "provider": "rajaongkir", "scan_limit": limit}
    if run_id:
        await _service_write("oto_integration_reconciliation_runs", "PATCH", {
            "status": run_status, "completed_at": finished, "scanned_count": len(intents),
            "matched_count": matched, "mismatch_count": mismatched, "failed_count": failed, "summary": summary,
        }, {"id": "eq." + run_id})
    return {"run_id": run_id, "provider": "rajaongkir", "status": run_status, "correlation_id": correlation,
            "scanned": len(intents), "matched": matched, "mismatched": mismatched, "failed": failed, "summary": summary}
