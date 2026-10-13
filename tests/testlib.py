from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
RESULTS = ROOT / "test-results"


class TestFailure(AssertionError):
    pass


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def request_json(base_url: str, method: str, path: str, payload: Any | None = None, timeout: int = 25) -> dict[str, Any]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base_url.rstrip("/") + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return {"status": resp.status, "body": json.loads(raw), "raw": raw}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"raw": raw}
        return {"status": exc.code, "body": parsed, "raw": raw}


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise TestFailure(message)


def assert_success(resp: dict[str, Any], label: str) -> dict[str, Any]:
    status = resp.get("status", 0)
    body = resp.get("body") or {}
    assert_true(status < 400, f"{label}: HTTP {status} {body}")
    assert_true(isinstance(body, dict), f"{label}: response is not JSON object")
    assert_true(body.get("success") is True, f"{label}: success is not true: {body}")
    return body.get("data")


def record_result(path: str, data: Any) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run_case(results: list[dict[str, Any]], name: str, fn) -> None:
    start = time.perf_counter()
    try:
        fn()
        results.append({"name": name, "status": "passed", "duration_ms": round((time.perf_counter() - start) * 1000, 1)})
        print(f"[PASS] {name}")
    except Exception as exc:
        results.append(
            {
                "name": name,
                "status": "failed",
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                "error": str(exc),
            }
        )
        print(f"[FAIL] {name}: {exc}")
