from __future__ import annotations

import asyncio
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.agents.orchestrator import _deterministic_content_audit, _offline_audit_report
from app.api.streaming import stream_live_operation
from app.llm.openai_compatible import OpenAICompatibleClient


class _StreamingHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    retry_post_count = 0

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        if not payload.get("stream"):
            type(self).retry_post_count += 1
            if type(self).retry_post_count < 3:
                body = b'{"error":"temporary upstream failure"}'
                self.send_response(503)
            else:
                body = json.dumps({"choices": [{"message": {"content": "retry-ok"}}]}).encode()
                self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        if payload.get("stream"):
            chunks = ["真实", "流式", "输出"]
            for chunk in chunks:
                event = {"choices": [{"delta": {"content": chunk}}]}
                self.wfile.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
                self.wfile.flush()
                time.sleep(0.08)
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

    def log_message(self, format: str, *args: object) -> None:
        return


class StreamingClientTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        _StreamingHandler.retry_post_count = 0
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _StreamingHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    async def asyncTearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    async def test_upstream_chunks_arrive_before_request_finishes(self) -> None:
        client = OpenAICompatibleClient(
            base_url=f"http://127.0.0.1:{self.server.server_port}",
            api_key="test-key",
            model="test-model",
            chat_path="/v1/chat/completions",
        )
        received: list[tuple[str, float]] = []
        started = time.perf_counter()

        async def on_chunk(text: str) -> None:
            received.append((text, time.perf_counter() - started))

        result = await client.chat_text(
            messages=[{"role": "user", "content": "test"}],
            on_chunk=on_chunk,
        )
        finished = time.perf_counter() - started

        self.assertEqual(result, "真实流式输出")
        self.assertEqual("".join(item[0] for item in received), "真实流式输出")
        self.assertLess(received[0][1], finished - 0.08)

    async def test_non_streaming_chat_retries_transient_upstream_failures(self) -> None:
        client = OpenAICompatibleClient(
            base_url=f"http://127.0.0.1:{self.server.server_port}",
            api_key="test-key",
            model="test-model",
            chat_path="/v1/chat/completions",
        )

        result = await client.chat_text(messages=[{"role": "user", "content": "retry"}])

        self.assertEqual(result, "retry-ok")
        self.assertEqual(_StreamingHandler.retry_post_count, 3)

    async def test_live_operation_timeout_ends_stream_without_persisting_partial_result(self) -> None:
        async def work(_on_chunk):
            await asyncio.sleep(1)
            return {"resource": {"id": "must-not-be-emitted"}}

        packets = [
            packet
            async for packet in stream_live_operation(
                request_id="timeout-contract",
                work=work,
                start_message="start",
                final_key="result",
                timeout_sec=0.05,
            )
        ]
        output = "".join(packets)
        self.assertIn('"event": "error"', output)
        self.assertIn("没有写入不完整结果", output)
        self.assertIn('"event": "done"', output)
        self.assertNotIn("must-not-be-emitted", output)


class BodyAuditTest(unittest.TestCase):
    def test_body_audit_flags_unverified_specific_reference(self) -> None:
        resources = [
            {
                "resource_id": "r1",
                "title": "测试讲义",
                "type": "lecture_doc",
                "content": "根据 ISO 99999:2099 和《不存在的教材》第 88 页，该结论必然成立。",
                "content_truncated": False,
            }
        ]
        findings = _deterministic_content_audit(resources, references=[])
        report = _offline_audit_report(resources, findings)

        self.assertEqual(report["overall_status"], "warning")
        self.assertTrue(findings[0]["unsupported_markers"])
        self.assertTrue(report["resources"][0]["citation_issues"])


if __name__ == "__main__":
    unittest.main()
