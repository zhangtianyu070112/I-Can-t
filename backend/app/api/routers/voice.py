from __future__ import annotations

import asyncio
import json
import os
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
from fastapi import APIRouter, Response, WebSocket, WebSocketDisconnect


router = APIRouter(prefix="/api/voice", tags=["voice"])


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _realtime_api_key() -> str:
    return (
        _env("VOICE_REALTIME_API_KEY")
        or _env("OPENAI_API_KEY")
    )


def _realtime_model() -> str:
    return _env("VOICE_REALTIME_MODEL")


def _realtime_url() -> str:
    explicit_url = _env("VOICE_REALTIME_SDP_URL") or _env("VOICE_REALTIME_WEBRTC_URL") or _env("VOICE_REALTIME_WS_URL")
    if explicit_url:
        url = explicit_url
    else:
        base_url = (_env("VOICE_REALTIME_BASE_URL") or _env("VOICE_TRANSCRIBE_BASE_URL")).rstrip("/")
        if not base_url:
            return ""
        endpoint = _env("VOICE_REALTIME_SDP_ENDPOINT", "/realtime")
        url = endpoint if endpoint.startswith(("http://", "https://", "ws://", "wss://")) else f"{base_url}{endpoint}"

    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if _realtime_model() and "model" not in query:
        query["model"] = [_realtime_model()]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def _transport() -> str:
    return "websocket" if urlparse(_realtime_url()).scheme.lower() in {"ws", "wss"} else "webrtc-sdp"


def _timeout() -> int:
    try:
        return int(_env("VOICE_REALTIME_TIMEOUT", "45"))
    except ValueError:
        return 45


def _extra_headers() -> dict[str, str]:
    raw = _env("VOICE_REALTIME_HEADERS_JSON")
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("VOICE_REALTIME_HEADERS_JSON must be a JSON object")
    return {str(key): str(value) for key, value in data.items()}


def _config_error() -> str | None:
    realtime_url = _realtime_url()
    if not realtime_url:
        return "Realtime voice is disabled. Configure VOICE_REALTIME_* to enable it."
    parsed = urlparse(realtime_url)
    if parsed.scheme.lower() not in {"http", "https", "ws", "wss"}:
        return "VOICE_REALTIME_URL 必须是 http(s) 或 ws(s) 地址，请不要把 API Key 填到 URL 配置里"
    if not _realtime_api_key():
        return "请配置 VOICE_REALTIME_API_KEY"
    try:
        _extra_headers()
    except Exception as exc:
        return f"VOICE_REALTIME_HEADERS_JSON 配置错误：{exc}"
    return None


@router.get("/realtime/config")
async def realtime_config() -> dict:
    config_error = _config_error()
    return {
        "enabled": config_error is None,
        "model": _realtime_model(),
        "transport": _transport(),
        "ws_path": "/api/voice/realtime/ws",
        "sdp_url_configured": bool(_env("VOICE_REALTIME_SDP_URL") or _env("VOICE_REALTIME_WEBRTC_URL") or _env("VOICE_REALTIME_WS_URL")),
        "base_url_configured": bool(_env("VOICE_REALTIME_BASE_URL") or _env("VOICE_TRANSCRIBE_BASE_URL")),
        "timeout": _timeout(),
        "config_error": config_error,
    }


@router.post("/realtime/sdp", response_model=None)
async def realtime_sdp(body: bytes):
    config_error = _config_error()
    if config_error:
        return {"error": f"Realtime 配置错误：{config_error}"}
    if _transport() == "websocket":
        return {"error": "当前 Realtime 地址是 WebSocket，请使用 /api/voice/realtime/ws"}

    offer = body.decode("utf-8", errors="replace")
    if not offer or "v=0" not in offer:
        return {"error": "未收到有效的 WebRTC SDP offer"}

    headers = {
        "Authorization": f"Bearer {_realtime_api_key()}",
        "Content-Type": "application/sdp",
        "Accept": "application/sdp",
        **_extra_headers(),
    }
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        resp = await client.post(_realtime_url(), content=offer.encode("utf-8"), headers=headers)
    if resp.status_code >= 400:
        return {"error": f"Realtime 服务返回 HTTP {resp.status_code}: {resp.text[:500]}"}
    return Response(resp.content, media_type="application/sdp")


async def _connect_upstream(url: str, headers: dict[str, str], timeout: int):
    import websockets

    try:
        return await websockets.connect(url, additional_headers=headers, open_timeout=timeout)
    except TypeError:
        return await websockets.connect(url, extra_headers=headers, open_timeout=timeout)


def _is_normal_websocket_close(exc: BaseException) -> bool:
    close_codes = {
        getattr(exc, "code", None),
        getattr(getattr(exc, "rcvd", None), "code", None),
        getattr(getattr(exc, "sent", None), "code", None),
    }
    if close_codes & {1000, 1001}:
        return True
    text = str(exc)
    return "1000 (OK)" in text or "1001" in text or exc.__class__.__name__ == "ConnectionClosedOK"


@router.websocket("/realtime/ws")
async def realtime_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    config_error = _config_error()
    if config_error:
        await websocket.send_text(json.dumps({"type": "error", "error": f"Realtime 配置错误：{config_error}"}, ensure_ascii=False))
        await websocket.close()
        return
    if _transport() != "websocket":
        await websocket.send_text(json.dumps({"type": "error", "error": "当前 Realtime 地址不是 WebSocket"}, ensure_ascii=False))
        await websocket.close()
        return

    headers = {"Authorization": f"Bearer {_realtime_api_key()}", **_extra_headers()}
    upstream = None
    try:
        upstream = await _connect_upstream(_realtime_url(), headers, _timeout())
        await websocket.send_text(json.dumps({"type": "proxy.connected", "model": _realtime_model(), "transport": "websocket"}, ensure_ascii=False))

        async def upstream_to_client() -> None:
            while True:
                message = await upstream.recv()
                if isinstance(message, bytes):
                    await websocket.send_bytes(message)
                else:
                    await websocket.send_text(message)

        async def client_to_upstream() -> None:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                if message.get("bytes") is not None:
                    await upstream.send(message["bytes"])
                elif message.get("text") is not None:
                    await upstream.send(message["text"])

        done, pending = await asyncio.wait(
            {asyncio.create_task(upstream_to_client()), asyncio.create_task(client_to_upstream())},
            return_when=asyncio.FIRST_EXCEPTION,
        )
        for task in pending:
            task.cancel()
        for task in done:
            exc = task.exception()
            if exc and _is_normal_websocket_close(exc):
                try:
                    await websocket.send_text(json.dumps({"type": "proxy.closed", "reason": "normal"}, ensure_ascii=False))
                except Exception:
                    pass
                continue
            if exc and not isinstance(exc, WebSocketDisconnect):
                raise exc
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        if _is_normal_websocket_close(exc):
            try:
                await websocket.send_text(json.dumps({"type": "proxy.closed", "reason": "normal"}, ensure_ascii=False))
            except Exception:
                pass
            return
        try:
            await websocket.send_text(json.dumps({"type": "error", "error": f"Realtime WebSocket 连接失败：{exc}"}, ensure_ascii=False))
        except Exception:
            pass
    finally:
        if upstream is not None:
            await upstream.close()
