from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import httpx

from app.core.config import settings


class OpenAICompatibleClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_sec: int = 60,
        chat_path: str = "/v1/chat/completions",
        auth_header: str = "Authorization",
        auth_prefix: str = "Bearer ",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_sec
        self._chat_path = chat_path if chat_path.startswith("/") else f"/{chat_path}"
        self._auth_header = auth_header
        self._auth_prefix = auth_prefix

    def _headers(self) -> dict[str, str]:
        if not self._auth_header:
            return {}
        prefix = self._auth_prefix or ""
        sep = ""
        if prefix and not prefix.endswith(" "):
            sep = " "
        return {self._auth_header: f"{prefix}{sep}{self._api_key}"}

    async def _post_chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        attempts = 3
        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(f"{self._base_url}{self._chat_path}", json=payload, headers=self._headers())
                    resp.raise_for_status()
                    return resp.json()
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code if e.response is not None else "unknown"
                retryable = status_code in {408, 429, 500, 502, 503, 504}
                if retryable and attempt < attempts - 1:
                    await asyncio.sleep(0.4 * (attempt + 1))
                    continue
                detail = e.response.text[:800] if e.response is not None else ""
                raise RuntimeError(f"LLM 请求失败：HTTP {status_code} {detail}") from e
            except httpx.TimeoutException as e:
                if attempt < attempts - 1:
                    await asyncio.sleep(0.4 * (attempt + 1))
                    continue
                raise RuntimeError(f"LLM 请求超时：{self._timeout} 秒内没有收到响应，请检查模型、网络或服务商状态。") from e
            except httpx.RequestError as e:
                if attempt < attempts - 1:
                    await asyncio.sleep(0.4 * (attempt + 1))
                    continue
                raise RuntimeError(f"LLM 网络请求失败：{e}") from e
        raise RuntimeError("LLM 请求失败：重试次数已用尽")

    async def _stream_chat(self, payload: dict[str, Any]) -> AsyncIterator[str]:
        payload = {**payload, "stream": True}
        try:
            timeout = httpx.Timeout(self._timeout, connect=min(self._timeout, 15))
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}{self._chat_path}",
                    json=payload,
                    headers={**self._headers(), "Accept": "text/event-stream"},
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line or line.startswith(":"):
                            continue
                        if line.startswith("data:"):
                            line = line[5:].strip()
                        if line == "[DONE]":
                            break
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        choices = event.get("choices") or []
                        if not choices:
                            continue
                        choice = choices[0] or {}
                        delta = choice.get("delta") or {}
                        content = delta.get("content")
                        if content is None:
                            content = (choice.get("message") or {}).get("content")
                        if content:
                            yield str(content)
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code if e.response is not None else "unknown"
            detail = (await e.response.aread()).decode(errors="replace")[:800] if e.response is not None else ""
            raise RuntimeError(f"LLM 流式请求失败：HTTP {status_code} {detail}") from e
        except httpx.TimeoutException as e:
            raise RuntimeError(f"LLM 流式请求超时：{self._timeout} 秒内没有收到响应。") from e
        except httpx.RequestError as e:
            raise RuntimeError(f"LLM 流式网络请求失败：{e}") from e

    async def _collect_stream(
        self,
        payload: dict[str, Any],
        on_chunk: Callable[[str], Awaitable[None]] | None,
    ) -> str:
        parts: list[str] = []
        callback_buffer: list[str] = []
        last_emit = time.monotonic()
        async for chunk in self._stream_chat(payload):
            parts.append(chunk)
            if on_chunk:
                callback_buffer.append(chunk)
                buffered = "".join(callback_buffer)
                now = time.monotonic()
                if len(buffered) >= 24 or now - last_emit >= 0.08:
                    await on_chunk(buffered)
                    callback_buffer.clear()
                    last_emit = now
        if on_chunk and callback_buffer:
            await on_chunk("".join(callback_buffer))
        return "".join(parts)

    async def chat_json(
        self,
        *,
        messages: list[dict[str, str]],
        schema_hint: str,
        system: str = "",
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        if not self._base_url or not self._api_key or not self._model:
            raise RuntimeError("LLM 未配置：请设置 LLM_BASE_URL/LLM_API_KEY/LLM_MODEL")

        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个严格输出 JSON 的助手。不要输出任何额外文本。",
                },
                *([{"role": "system", "content": system}] if system else []),
                {
                    "role": "system",
                    "content": f"输出 JSON 的结构要求：{schema_hint}",
                },
                *messages,
            ],
            "temperature": 0.3,
        }
        if on_chunk:
            content = await self._collect_stream(payload, on_chunk)
        else:
            data = await self._post_chat(payload)
            content = data["choices"][0]["message"]["content"]
        parsed = parse_json_content(content)
        if not isinstance(parsed, dict):
            raise RuntimeError("模型返回的 JSON 顶层结构应为对象，请重新生成。")
        return parsed

    async def chat_text(
        self,
        *,
        messages: list[dict[str, str]],
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int | None = None,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        if not self._base_url or not self._api_key or not self._model:
            raise RuntimeError("LLM 未配置：请设置 LLM_BASE_URL/LLM_API_KEY/LLM_MODEL")

        payload = {
            "model": self._model,
            "messages": ([{"role": "system", "content": system}] if system else []) + messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max(128, min(int(max_tokens), 8192))
        if on_chunk:
            return await self._collect_stream(payload, on_chunk)
        data = await self._post_chat(payload)
        return data["choices"][0]["message"]["content"]


def _strip_json_fence(content: str) -> str:
    text = (content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def parse_json_content(content: str) -> Any:
    """Parse common model JSON defects without leaking decoder errors to UI."""
    text = _strip_json_fence(content)
    candidates = [text]
    for opening, closing in (("{", "}"), ("[", "]")):
        start = text.find(opening)
        end = text.rfind(closing)
        if start >= 0 and end > start:
            extracted = text[start : end + 1]
            if extracted not in candidates:
                candidates.append(extracted)

    last_error: Exception | None = None
    for candidate in candidates:
        repaired_backslashes = re.sub(r'(?<!\\)\\(?!["\\/bfnrtu])', r'\\\\', candidate)
        repaired_quotes = _escape_inner_json_quotes(repaired_backslashes)
        for attempt in (candidate, repaired_backslashes, repaired_quotes):
            try:
                return json.loads(attempt, strict=False)
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = exc
    raise RuntimeError("模型返回的 JSON 含有未转义字符或结构不完整，请重新生成。") from last_error


def _escape_inner_json_quotes(text: str) -> str:
    output: list[str] = []
    in_string = False
    escaped = False
    length = len(text)
    for index, char in enumerate(text):
        if not in_string:
            output.append(char)
            if char == '"':
                in_string = True
            continue
        if escaped:
            output.append(char)
            escaped = False
            continue
        if char == "\\":
            output.append(char)
            escaped = True
            continue
        if char != '"':
            output.append(char)
            continue
        next_index = index + 1
        while next_index < length and text[next_index].isspace():
            next_index += 1
        if next_index >= length or text[next_index] in ":,}]":
            output.append(char)
            in_string = False
        else:
            output.append('\\"')
    return "".join(output)


def get_llm_client() -> OpenAICompatibleClient:
    return OpenAICompatibleClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        timeout_sec=settings.llm_timeout_sec,
        chat_path=settings.llm_chat_path,
        auth_header=settings.llm_auth_header,
        auth_prefix=settings.llm_auth_prefix,
    )
