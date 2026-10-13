from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api/avatar", tags=["avatar"])


_NO_STORE_HEADERS = {
    "Cache-Control": "no-store, private, max-age=0",
    "Pragma": "no-cache",
}
_MAX_ACTIVE_GRANTS = 256
_MAX_GATEWAY_BODY_BYTES = 64 * 1024
_DEFAULT_ALLOWED_BROWSER_ORIGINS = frozenset(
    {
        "http://127.0.0.1:4173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://localhost:5173",
    }
)
_ALLOWED_GATEWAY_PAYLOAD_KEYS = {
    "POST": frozenset({"tag", "gateway_type", "config"}),
    "DELETE": frozenset({"session_id", "stop_reason"}),
}


@dataclass
class _AvatarGatewayGrant:
    app_id: str
    secret: str = field(repr=False)
    upstream_url: str
    start_expires_at: float
    active_expires_at: float | None = None
    session_id: str = ""
    session_ids: set[str] = field(default_factory=set)
    start_count: int = 0
    start_in_progress: bool = False


class _AvatarGatewayCapacityError(RuntimeError):
    pass


_gateway_grants: dict[str, _AvatarGatewayGrant] = {}
_gateway_grants_lock = threading.Lock()


class AvatarSpeakRequest(BaseModel):
    session_id: str | None = None
    text: str
    interrupt: bool = True
    meta: dict[str, Any] = Field(default_factory=dict)


class AvatarSessionRequest(BaseModel):
    student_id: str | None = None
    avatar_id: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class AvatarStopRequest(BaseModel):
    session_id: str | None = None


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _json_env(name: str) -> dict[str, str]:
    raw = _env(name)
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{name} must be a JSON object")
    return {str(key): str(value) for key, value in data.items()}


def _provider() -> str:
    return (_env("AVATAR_PROVIDER") or "xingyuan").lower()


def _base_url() -> str:
    return _env("XINGYUAN_AVATAR_BASE_URL").rstrip("/")


def _app_id() -> str:
    return _env("XINGYUAN_APP_ID")


def _app_secret() -> str:
    return _env("XINGYUAN_APP_SECRET")


def _timeout() -> float:
    try:
        return float(_env("XINGYUAN_AVATAR_TIMEOUT", "30"))
    except ValueError:
        return 30.0


def _now_seconds() -> float:
    return time.time()


def _bounded_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(_env(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


def _grant_ttl_seconds() -> int:
    return _bounded_int_env("XINGYUAN_AVATAR_GRANT_TTL_SECONDS", 120, 30, 300)


def _signature_skew_seconds() -> int:
    return _bounded_int_env("XINGYUAN_AVATAR_SIGNATURE_SKEW_SECONDS", 60, 5, 120)


def _active_session_ttl_seconds() -> int:
    return _bounded_int_env("XINGYUAN_AVATAR_ACTIVE_SESSION_TTL_SECONDS", 3600, 300, 7200)


def _max_session_starts_per_grant() -> int:
    return _bounded_int_env("XINGYUAN_AVATAR_MAX_SESSION_STARTS_PER_GRANT", 3, 1, 5)


def _max_active_grants() -> int:
    return _bounded_int_env("XINGYUAN_AVATAR_MAX_ACTIVE_GRANTS", _MAX_ACTIVE_GRANTS, 1, 1024)


def _url(path_env: str, default_path: str) -> str:
    path = _env(path_env, default_path)
    if path.startswith(("http://", "https://")):
        return path
    return f"{_base_url()}/{path.lstrip('/')}"


def _prune_gateway_grants(now: float) -> None:
    expired = [
        grant_id
        for grant_id, grant in _gateway_grants.items()
        if (grant.active_expires_at or grant.start_expires_at) <= now
    ]
    for grant_id in expired:
        _gateway_grants.pop(grant_id, None)


def _issue_gateway_grant() -> tuple[str, _AvatarGatewayGrant]:
    now = _now_seconds()
    ttl = _grant_ttl_seconds()
    grant = _AvatarGatewayGrant(
        app_id=_app_id(),
        secret=secrets.token_urlsafe(32),
        upstream_url=_url("XINGYUAN_AVATAR_SESSION_PATH", "/user/v1/ttsa/session"),
        start_expires_at=now + ttl,
    )
    grant_id = secrets.token_urlsafe(24)
    with _gateway_grants_lock:
        _prune_gateway_grants(now)
        if len(_gateway_grants) >= _max_active_grants():
            raise _AvatarGatewayCapacityError
        _gateway_grants[grant_id] = grant
    return grant_id, grant


def _json_no_store(payload: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code, headers=_NO_STORE_HEADERS)


def _gateway_error(status_code: int, code: str, message: str) -> JSONResponse:
    return _json_no_store(
        {"success": False, "error_code": code, "error_reason": message},
        status_code=status_code,
    )


def _browser_origin_allowed(request: Request) -> bool:
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        return False
    origin = request.headers.get("origin", "").strip().rstrip("/")
    if not origin:
        return True
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
        return False
    same_origin = f"{request.url.scheme}://{request.headers.get('host', '')}".rstrip("/")
    configured = {
        item.strip().rstrip("/")
        for item in _env("XINGYUAN_AVATAR_ALLOWED_ORIGINS").split(",")
        if item.strip() and item.strip() != "*"
    }
    return origin == same_origin or origin in (_DEFAULT_ALLOWED_BROWSER_ORIGINS | configured)


def _canonical_json(payload: Any) -> str:
    # This intentionally mirrors xmovAvatar's headersNeedSign implementation:
    # recursively sorted object keys, compact UTF-8 JSON, then removal of ASCII spaces.
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).replace(" ", "")


def _signature_path(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return path


def _sdk_signature(
    app_secret: str,
    method: str,
    url: str,
    payload: dict[str, Any],
    timestamp: str,
) -> str:
    source = (
        f"{_signature_path(url).lower()}"
        f"{method.lower()}"
        f"{_canonical_json(payload)}"
        f"{app_secret}"
        f"{timestamp}"
    )
    return hashlib.md5(source.encode("utf-8")).hexdigest()  # noqa: S324 - vendor protocol


def _get_gateway_grant(grant_id: str, now: float) -> _AvatarGatewayGrant | None:
    with _gateway_grants_lock:
        _prune_gateway_grants(now)
        return _gateway_grants.get(grant_id)


def _reserve_gateway_operation(
    grant_id: str,
    grant: _AvatarGatewayGrant,
    method: str,
    payload: dict[str, Any],
) -> tuple[int, str, str] | None:
    with _gateway_grants_lock:
        if _gateway_grants.get(grant_id) is not grant:
            return (401, "AVATAR_GATEWAY_GRANT_INVALID", "avatar gateway grant is invalid or expired")
        if method == "POST":
            if grant.start_in_progress:
                return (409, "AVATAR_GATEWAY_START_IN_PROGRESS", "avatar gateway session start is in progress")
            if grant.start_count >= _max_session_starts_per_grant():
                return (429, "AVATAR_GATEWAY_START_LIMIT", "avatar gateway session start limit was reached")
            grant.start_in_progress = True
            return None
        requested_session_id = str(payload.get("session_id") or "").strip()
        if not grant.session_ids:
            return (409, "AVATAR_GATEWAY_SESSION_NOT_STARTED", "avatar gateway session has not started")
        if not any(hmac.compare_digest(requested_session_id, item) for item in grant.session_ids):
            return (403, "AVATAR_GATEWAY_SESSION_FORBIDDEN", "avatar gateway grant does not own this session")
        return None


def _release_start_reservation(grant_id: str, grant: _AvatarGatewayGrant) -> None:
    with _gateway_grants_lock:
        if _gateway_grants.get(grant_id) is grant:
            grant.start_in_progress = False


def _extract_session_id(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("session_id", "sessionId"):
            session_id = str(value.get(key) or "").strip()
            if session_id:
                return session_id
        for item in value.values():
            session_id = _extract_session_id(item)
            if session_id:
                return session_id
    elif isinstance(value, list):
        for item in value:
            session_id = _extract_session_id(item)
            if session_id:
                return session_id
    return ""


def _activate_gateway_session(
    grant_id: str,
    grant: _AvatarGatewayGrant,
    session_id: str,
    now: float,
) -> None:
    with _gateway_grants_lock:
        if _gateway_grants.get(grant_id) is grant:
            grant.start_in_progress = False
            grant.session_id = session_id
            grant.session_ids.add(session_id)
            grant.start_count += 1
            grant.active_expires_at = now + _active_session_ttl_seconds()


def _revoke_gateway_grant(grant_id: str, grant: _AvatarGatewayGrant) -> None:
    with _gateway_grants_lock:
        if _gateway_grants.get(grant_id) is grant:
            _gateway_grants.pop(grant_id, None)


def _decode_gateway_payload(raw_body: bytes, method: str) -> dict[str, Any] | None:
    if not raw_body or len(raw_body) > _MAX_GATEWAY_BODY_BYTES:
        return None
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    allowed_keys = _ALLOWED_GATEWAY_PAYLOAD_KEYS[method]
    if not set(payload).issubset(allowed_keys):
        return None
    if method == "POST" and not isinstance(payload.get("config"), dict):
        return None
    if method == "DELETE" and not str(payload.get("session_id") or "").strip():
        return None
    return payload


def _sanitize_upstream_payload(value: Any, forbidden_values: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).lower().replace("-", "").replace("_", "")
            if normalized_key in {"appsecret", "xappsecret", "authorization"}:
                continue
            sanitized[str(key)] = _sanitize_upstream_payload(item, forbidden_values)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_upstream_payload(item, forbidden_values) for item in value]
    if isinstance(value, str):
        sanitized_text = value
        for forbidden in forbidden_values:
            if forbidden:
                sanitized_text = sanitized_text.replace(forbidden, "[redacted]")
        return sanitized_text
    return value


def _xingyuan_headers() -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-App-Id": _app_id(),
        "X-App-Secret": _app_secret(),
        "App-Id": _app_id(),
        "App-Secret": _app_secret(),
        **_json_env("XINGYUAN_AVATAR_HEADERS_JSON"),
    }
    auth_header = _env("XINGYUAN_AVATAR_AUTH_HEADER")
    auth_prefix = _env("XINGYUAN_AVATAR_AUTH_PREFIX")
    auth_token = _env("XINGYUAN_AVATAR_AUTH_TOKEN")
    if auth_header and auth_token:
        headers[auth_header] = f"{auth_prefix}{auth_token}"
    return {key: value for key, value in headers.items() if value}


def _config_error() -> str | None:
    if _provider() != "xingyuan":
        return "当前仅配置了星元具身数字人适配器"
    if not _app_id() or not _app_secret():
        return "请配置 XINGYUAN_APP_ID 和 XINGYUAN_APP_SECRET"
    if not _base_url():
        return "请配置 XINGYUAN_AVATAR_BASE_URL 以及接口路径"
    try:
        _json_env("XINGYUAN_AVATAR_HEADERS_JSON")
    except Exception as exc:
        return f"XINGYUAN_AVATAR_HEADERS_JSON 配置错误：{exc}"
    return None


async def _post_json(path_env: str, default_path: str, payload: dict[str, Any]) -> dict[str, Any]:
    config_error = _config_error()
    if config_error:
        return {"success": False, "error": config_error, "fallback": "canvas"}

    async with httpx.AsyncClient(timeout=_timeout()) as client:
        response = await client.post(_url(path_env, default_path), json=payload, headers=_xingyuan_headers())

    if response.status_code >= 400:
        return {
            "success": False,
            "error": f"星元具身接口返回 HTTP {response.status_code}",
            "detail": response.text[:500],
            "fallback": "canvas",
        }
    data = response.json()
    if isinstance(data, dict):
        return {"success": True, "provider": "xingyuan", **data}
    return {"success": True, "provider": "xingyuan", "data": data}


@router.get("/config")
async def avatar_config() -> dict[str, Any]:
    config_error = _config_error()
    return {
        "enabled": config_error is None,
        "provider": _provider(),
        "credentials_configured": bool(_app_id() and _app_secret()),
        "base_url_configured": bool(_base_url()),
        "session_path_configured": bool(_env("XINGYUAN_AVATAR_SESSION_PATH")),
        "speak_path_configured": bool(_env("XINGYUAN_AVATAR_SPEAK_PATH")),
        "stop_path_configured": bool(_env("XINGYUAN_AVATAR_STOP_PATH")),
        "config_error": config_error,
    }


@router.get("/sdk-config")
async def avatar_sdk_config(request: Request) -> JSONResponse:
    if not _browser_origin_allowed(request):
        return _gateway_error(403, "AVATAR_ORIGIN_FORBIDDEN", "avatar credentials are not available to this origin")
    config_error = _config_error()
    grant_id = ""
    grant: _AvatarGatewayGrant | None = None
    if config_error is None:
        try:
            grant_id, grant = _issue_gateway_grant()
        except _AvatarGatewayCapacityError:
            return _gateway_error(
                429,
                "AVATAR_GATEWAY_CAPACITY",
                "avatar gateway has too many active grants; retry after an existing grant expires",
            )
    ttl = _grant_ttl_seconds() if grant else 0
    expires_at = (
        datetime.fromtimestamp(grant.start_expires_at, tz=timezone.utc).isoformat()
        if grant
        else None
    )
    payload = {
        "enabled": config_error is None,
        "provider": _provider(),
        "appId": grant.app_id if grant else "",
        "appSecret": grant.secret if grant else "",
        "gatewayServer": f"/api/avatar/sdk-gateway/{grant_id}" if grant else "",
        "headers": {},
        "hardwareAcceleration": _env("XINGYUAN_AVATAR_HARDWARE_ACCELERATION", "prefer-hardware"),
        "config_error": config_error,
        "credentialMode": "ephemeral_proxy" if grant else "disabled",
        "expiresAt": expires_at,
        "expiresInSeconds": ttl,
    }
    return _json_no_store(payload)


@router.api_route("/sdk-gateway/{grant_id}", methods=["POST", "DELETE"])
async def avatar_sdk_gateway(grant_id: str, request: Request) -> JSONResponse:
    if not _browser_origin_allowed(request):
        return _gateway_error(403, "AVATAR_ORIGIN_FORBIDDEN", "avatar gateway is not available to this origin")
    method = request.method.upper()
    if method not in _ALLOWED_GATEWAY_PAYLOAD_KEYS or request.url.query:
        return _gateway_error(405, "AVATAR_GATEWAY_METHOD_NOT_ALLOWED", "avatar gateway request is not allowed")

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > _MAX_GATEWAY_BODY_BYTES:
                return _gateway_error(413, "AVATAR_GATEWAY_BODY_TOO_LARGE", "avatar gateway body is too large")
        except ValueError:
            return _gateway_error(400, "AVATAR_GATEWAY_INVALID_BODY", "avatar gateway body is invalid")

    raw_body = await request.body()
    if len(raw_body) > _MAX_GATEWAY_BODY_BYTES:
        return _gateway_error(413, "AVATAR_GATEWAY_BODY_TOO_LARGE", "avatar gateway body is too large")
    payload = _decode_gateway_payload(raw_body, method)
    if payload is None:
        return _gateway_error(400, "AVATAR_GATEWAY_INVALID_BODY", "avatar gateway body is invalid")

    now = _now_seconds()
    grant = _get_gateway_grant(grant_id, now)
    if grant is None:
        return _gateway_error(401, "AVATAR_GATEWAY_GRANT_INVALID", "avatar gateway grant is invalid or expired")

    app_id = request.headers.get("X-APP-ID", "")
    provided_token = request.headers.get("X-TOKEN", "")
    timestamp = request.headers.get("X-TIMESTAMP", "")
    try:
        timestamp_value = int(timestamp)
    except ValueError:
        return _gateway_error(401, "AVATAR_GATEWAY_SIGNATURE_INVALID", "avatar gateway signature is invalid")
    if abs(now - timestamp_value) > _signature_skew_seconds():
        return _gateway_error(401, "AVATAR_GATEWAY_SIGNATURE_EXPIRED", "avatar gateway signature has expired")
    if not hmac.compare_digest(app_id, grant.app_id):
        return _gateway_error(401, "AVATAR_GATEWAY_SIGNATURE_INVALID", "avatar gateway signature is invalid")
    expected_token = _sdk_signature(grant.secret, method, request.url.path, payload, timestamp)
    if not provided_token or not hmac.compare_digest(provided_token.lower(), expected_token):
        return _gateway_error(401, "AVATAR_GATEWAY_SIGNATURE_INVALID", "avatar gateway signature is invalid")

    reservation_error = _reserve_gateway_operation(grant_id, grant, method, payload)
    if reservation_error:
        return _gateway_error(*reservation_error)

    upstream_timestamp = str(int(now))
    upstream_headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-APP-ID": _app_id(),
        "X-TOKEN": _sdk_signature(_app_secret(), method, grant.upstream_url, payload, upstream_timestamp),
        "X-TIMESTAMP": upstream_timestamp,
    }
    try:
        async with httpx.AsyncClient(timeout=_timeout(), follow_redirects=False) as client:
            upstream_response = await client.request(
                method,
                grant.upstream_url,
                content=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                headers=upstream_headers,
            )
    except httpx.HTTPError:
        if method == "POST":
            _release_start_reservation(grant_id, grant)
        return _gateway_error(502, "AVATAR_GATEWAY_UPSTREAM_UNAVAILABLE", "avatar gateway upstream is unavailable")

    try:
        upstream_payload = upstream_response.json()
    except ValueError:
        if method == "POST":
            _release_start_reservation(grant_id, grant)
        return _gateway_error(502, "AVATAR_GATEWAY_UPSTREAM_INVALID", "avatar gateway upstream returned invalid JSON")

    upstream_succeeded = 200 <= upstream_response.status_code < 300
    if method == "POST":
        if upstream_succeeded:
            session_id = _extract_session_id(upstream_payload)
            if not session_id:
                _release_start_reservation(grant_id, grant)
                return _gateway_error(
                    502,
                    "AVATAR_GATEWAY_UPSTREAM_INVALID",
                    "avatar gateway upstream response did not contain a session id",
                )
            _activate_gateway_session(grant_id, grant, session_id, now)
        else:
            _release_start_reservation(grant_id, grant)
    elif upstream_succeeded:
        _revoke_gateway_grant(grant_id, grant)
    forbidden_values = (_app_secret(), _env("XINGYUAN_AVATAR_AUTH_TOKEN"))
    sanitized_payload = _sanitize_upstream_payload(upstream_payload, forbidden_values)
    return _json_no_store(sanitized_payload, status_code=upstream_response.status_code)


@router.post("/session")
async def create_avatar_session(request: AvatarSessionRequest) -> dict[str, Any]:
    payload = {
        "app_id": _app_id(),
        "appId": _app_id(),
        "appSecret": _app_secret(),
        "avatar_id": request.avatar_id or _env("XINGYUAN_AVATAR_ID"),
        "avatarId": request.avatar_id or _env("XINGYUAN_AVATAR_ID"),
        "student_id": request.student_id,
        "studentId": request.student_id,
        "meta": request.meta,
    }
    return await _post_json("XINGYUAN_AVATAR_SESSION_PATH", "/avatar/session", payload)


@router.post("/speak")
async def avatar_speak(request: AvatarSpeakRequest) -> dict[str, Any]:
    payload = {
        "app_id": _app_id(),
        "appId": _app_id(),
        "appSecret": _app_secret(),
        "session_id": request.session_id,
        "sessionId": request.session_id,
        "text": request.text,
        "interrupt": request.interrupt,
        "voice": _env("XINGYUAN_AVATAR_VOICE"),
        "meta": request.meta,
    }
    return await _post_json("XINGYUAN_AVATAR_SPEAK_PATH", "/avatar/speak", payload)


@router.post("/interrupt")
async def avatar_interrupt(request: AvatarStopRequest) -> dict[str, Any]:
    payload = {"app_id": _app_id(), "session_id": request.session_id}
    return await _post_json("XINGYUAN_AVATAR_INTERRUPT_PATH", "/avatar/interrupt", payload)


@router.post("/stop")
async def avatar_stop(request: AvatarStopRequest) -> dict[str, Any]:
    payload = {"app_id": _app_id(), "session_id": request.session_id}
    return await _post_json("XINGYUAN_AVATAR_STOP_PATH", "/avatar/stop", payload)
