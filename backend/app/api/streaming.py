from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from fastapi.responses import StreamingResponse


def sse(event: str, data: Any = None) -> str:
    payload = {"event": event, "data": data}
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def stream_response(generator: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def emit_text_chunks(text: str, *, path: str, size: int = 36) -> AsyncIterator[str]:
    text = text or ""
    for idx in range(0, len(text), size):
        yield sse("chunk", {"path": path, "text": text[idx : idx + size]})
        await asyncio.sleep(0.012)


async def stream_operation(
    *,
    request_id: str,
    work: Callable[[], Awaitable[Any]],
    start_message: str,
    final_key: str,
    chunk_text: Callable[[Any], str] | None = None,
    chunk_path: str = "text",
) -> AsyncIterator[str]:
    yield sse("start", {"request_id": request_id, "message": start_message})
    yield sse("status", {"message": "正在调用智能体服务"})
    try:
        result = await work()
        text = chunk_text(result) if chunk_text else ""
        if text:
            yield sse("status", {"message": "正在流式输出结果"})
            async for chunk in emit_text_chunks(text, path=chunk_path):
                yield chunk
        yield sse("final", {final_key: result, "request_id": request_id})
        yield sse("done", {"request_id": request_id})
    except Exception as e:
        yield sse("error", {"request_id": request_id, "message": str(e)})
        yield sse("done", {"request_id": request_id})


async def stream_live_operation(
    *,
    request_id: str,
    work: Callable[[Callable[[str], Awaitable[None]]], Awaitable[Any]],
    start_message: str,
    final_key: str,
    chunk_path: str = "text",
    fallback_text: Callable[[Any], str] | None = None,
    timeout_sec: float = 120.0,
) -> AsyncIterator[str]:
    """Forward upstream model deltas while the business operation is running."""
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
    emitted = False

    async def on_chunk(text: str) -> None:
        if text:
            await queue.put(("chunk", text))

    async def run() -> None:
        try:
            result = await work(on_chunk)
            await queue.put(("result", result))
        except Exception as exc:
            await queue.put(("error", exc))

    yield sse("start", {"request_id": request_id, "message": start_message})
    yield sse("status", {"message": "已连接模型，正在接收实时输出"})
    task = asyncio.create_task(run())
    deadline = time.monotonic() + max(0.01, timeout_sec)
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"真实模型处理超过 {int(timeout_sec)} 秒，任务已停止且没有写入不完整结果")
            kind, value = await asyncio.wait_for(queue.get(), timeout=remaining)
            if kind == "chunk":
                emitted = True
                yield sse("chunk", {"path": chunk_path, "text": value})
                continue
            if kind == "error":
                raise value

            result = value
            if not emitted and fallback_text:
                text = fallback_text(result)
                if text:
                    async for chunk in emit_text_chunks(text, path=chunk_path):
                        yield chunk
            yield sse("final", {final_key: result, "request_id": request_id})
            yield sse("done", {"request_id": request_id})
            break
    except asyncio.TimeoutError:
        yield sse(
            "error",
            {
                "request_id": request_id,
                "message": f"真实模型处理超过 {int(timeout_sec)} 秒，任务已停止且没有写入不完整结果",
            },
        )
        yield sse("done", {"request_id": request_id})
    except Exception as exc:
        yield sse("error", {"request_id": request_id, "message": str(exc)})
        yield sse("done", {"request_id": request_id})
    finally:
        if not task.done():
            task.cancel()
