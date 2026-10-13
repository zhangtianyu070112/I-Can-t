from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8000"


CHECKS = [
    ("GET", "/api/health", None),
    ("GET", "/api/avatar/config", None),
    ("GET", "/api/voice/realtime/config", None),
    ("GET", "/api/knowledge/map?student_id=demo&max_nodes=24", None),
    ("POST", "/api/knowledge/search", {"student_id": "demo", "query": "需求分析"}),
    ("POST", "/api/workshop/create", {"student_id": "demo", "topic": "软件需求分析与建模", "resource_type": "lecture_doc"}),
    ("GET", "/api/workshop/resources?student_id=demo", None),
    ("POST", "/api/recommendations", {"student_id": "demo"}),
    ("GET", "/api/exercises?student_id=demo&limit=3", None),
    ("GET", "/api/evaluation/snapshot?student_id=demo", None),
    ("POST", "/api/evaluation/generate", {"student_id": "demo"}),
]


def request(method: str, path: str, payload: dict | None) -> tuple[int, dict]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode("utf-8")
        return resp.status, json.loads(body)


def main() -> int:
    failures: list[str] = []
    for method, path, payload in CHECKS:
        label = f"{method} {path}"
        try:
            status, body = request(method, path, payload)
            success = body.get("success", True)
            if status >= 400 or success is False:
                failures.append(f"{label} -> status={status}, body={body}")
                print(f"[FAIL] {label}")
            else:
                print(f"[ OK ] {label}")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            failures.append(f"{label} -> HTTP {exc.code}: {raw}")
            print(f"[FAIL] {label}")
        except Exception as exc:
            failures.append(f"{label} -> {exc}")
            print(f"[FAIL] {label}")

    if failures:
        print("\nFailures:")
        for item in failures:
            print(f"- {item}")
        return 1
    print("\nBackend smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
