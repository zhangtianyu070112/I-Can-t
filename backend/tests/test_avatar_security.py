from __future__ import annotations

import hashlib
import json
import os
import time
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers import avatar as avatar_module
from app.api.routers.avatar import router


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).replace(" ", "")


def _sdk_token(path: str, method: str, payload: object, secret: str, timestamp: str) -> str:
    source = f"{path.lower()}{method.lower()}{_canonical_json(payload)}{secret}{timestamp}"
    return hashlib.md5(source.encode("utf-8")).hexdigest()  # noqa: S324 - vendor protocol


class AvatarSdkSecurityTest(unittest.TestCase):
    def setUp(self) -> None:
        with avatar_module._gateway_grants_lock:
            avatar_module._gateway_grants.clear()
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)
        self.env = {
            "AVATAR_PROVIDER": "xingyuan",
            "XINGYUAN_APP_ID": "upstream-app-id",
            "XINGYUAN_APP_SECRET": "upstream-secret-must-not-leave-server",
            "XINGYUAN_AVATAR_BASE_URL": "https://avatar-provider.test",
            "XINGYUAN_AVATAR_SESSION_PATH": "/user/v1/ttsa/session",
            "XINGYUAN_AVATAR_HEADERS_JSON": '{"Authorization":"Bearer upstream-token"}',
        }

    def tearDown(self) -> None:
        self.client.close()
        with avatar_module._gateway_grants_lock:
            avatar_module._gateway_grants.clear()

    def test_sdk_config_returns_compatible_ephemeral_credentials_without_upstream_secrets(self) -> None:
        with patch.dict(os.environ, self.env, clear=True):
            response = self.client.get("/api/avatar/sdk-config")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["provider"], "xingyuan")
        self.assertEqual(payload["appId"], self.env["XINGYUAN_APP_ID"])
        self.assertTrue(payload["appSecret"])
        self.assertNotEqual(payload["appSecret"], self.env["XINGYUAN_APP_SECRET"])
        self.assertTrue(payload["gatewayServer"].startswith("/api/avatar/sdk-gateway/"))
        self.assertEqual(payload["headers"], {})
        self.assertEqual(payload["credentialMode"], "ephemeral_proxy")
        self.assertGreater(payload["expiresInSeconds"], 0)
        self.assertNotIn(self.env["XINGYUAN_APP_SECRET"], response.text)
        self.assertNotIn("upstream-token", response.text)
        self.assertIn("no-store", response.headers.get("cache-control", ""))

    def test_sdk_config_refuses_new_grants_at_capacity_without_evicting_active_credentials(self) -> None:
        env = {**self.env, "XINGYUAN_AVATAR_MAX_ACTIVE_GRANTS": "1"}
        with patch.dict(os.environ, env, clear=True):
            first = self.client.get("/api/avatar/sdk-config")
            second = self.client.get("/api/avatar/sdk-config")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json()["error_code"], "AVATAR_GATEWAY_CAPACITY")
        self.assertNotIn(self.env["XINGYUAN_APP_SECRET"], second.text)
        self.assertIn("no-store", second.headers.get("cache-control", ""))

    def test_gateway_verifies_ephemeral_signature_and_resigns_upstream_without_leaking_secrets(self) -> None:
        captured: dict[str, object] = {}

        def upstream_handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            captured["url"] = str(request.url)
            captured["body"] = body
            captured["headers"] = dict(request.headers)
            upstream_timestamp = request.headers["X-TIMESTAMP"]
            expected_upstream_token = _sdk_token(
                "/user/v1/ttsa/session",
                "POST",
                body,
                self.env["XINGYUAN_APP_SECRET"],
                upstream_timestamp,
            )
            self.assertEqual(request.headers["X-TOKEN"], expected_upstream_token)
            return httpx.Response(
                200,
                json={
                    "data": {"session_id": "session-1", "resource_pack": {"name": "avatar-pack"}},
                    "appSecret": self.env["XINGYUAN_APP_SECRET"],
                    "message": f"echo {self.env['XINGYUAN_APP_SECRET']}",
                },
            )

        real_async_client = httpx.AsyncClient
        transport = httpx.MockTransport(upstream_handler)

        with patch.dict(os.environ, self.env, clear=True):
            config = self.client.get("/api/avatar/sdk-config").json()
            payload = {
                "tag": "competition-demo",
                "gateway_type": "default",
                "config": {"walk_version": 3, "nested": {"z": 2, "a": "has space"}},
            }
            timestamp = str(int(time.time()))
            token = _sdk_token(config["gatewayServer"], "POST", payload, config["appSecret"], timestamp)
            with patch(
                "app.api.routers.avatar.httpx.AsyncClient",
                side_effect=lambda *args, **kwargs: real_async_client(transport=transport),
            ):
                response = self.client.post(
                    config["gatewayServer"],
                    json=payload,
                    headers={
                        "X-APP-ID": config["appId"],
                        "X-TOKEN": token,
                        "X-TIMESTAMP": timestamp,
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["url"], "https://avatar-provider.test/user/v1/ttsa/session")
        self.assertEqual(captured["body"], payload)
        upstream_headers = captured["headers"]
        self.assertEqual(upstream_headers["x-app-id"], self.env["XINGYUAN_APP_ID"])
        self.assertNotIn("x-app-secret", upstream_headers)
        self.assertNotIn("app-secret", upstream_headers)
        self.assertNotIn("authorization", upstream_headers)
        self.assertNotIn(self.env["XINGYUAN_APP_SECRET"], response.text)
        self.assertNotIn("appSecret", response.json())
        self.assertEqual(response.json()["data"]["session_id"], "session-1")
        self.assertIn("no-store", response.headers.get("cache-control", ""))

    def test_untrusted_browser_origin_cannot_obtain_avatar_credentials(self) -> None:
        with patch.dict(os.environ, self.env, clear=True):
            response = self.client.get(
                "/api/avatar/sdk-config",
                headers={"Origin": "https://attacker.example", "Sec-Fetch-Site": "cross-site"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertNotIn(self.env["XINGYUAN_APP_SECRET"], response.text)
        self.assertNotIn("appSecret", response.text)
        self.assertIn("no-store", response.headers.get("cache-control", ""))

    def test_sdk_grants_are_unique_and_cannot_start_a_session_after_expiry(self) -> None:
        env = {**self.env, "XINGYUAN_AVATAR_GRANT_TTL_SECONDS": "30"}
        with patch.dict(os.environ, env, clear=True), patch(
            "app.api.routers.avatar.time.time", return_value=1_000.0
        ):
            first = self.client.get("/api/avatar/sdk-config").json()
            second = self.client.get("/api/avatar/sdk-config").json()

        self.assertNotEqual(first["appSecret"], second["appSecret"])
        self.assertNotEqual(first["gatewayServer"], second["gatewayServer"])

        payload = {"config": {"walk_version": 3}}
        expired_timestamp = "1031"
        token = _sdk_token(
            first["gatewayServer"], "POST", payload, first["appSecret"], expired_timestamp
        )
        with patch.dict(os.environ, env, clear=True), patch(
            "app.api.routers.avatar.time.time", return_value=1_031.0
        ):
            response = self.client.post(
                first["gatewayServer"],
                json=payload,
                headers={
                    "X-APP-ID": first["appId"],
                    "X-TOKEN": token,
                    "X-TIMESTAMP": expired_timestamp,
                },
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error_code"], "AVATAR_GATEWAY_GRANT_INVALID")

    def test_gateway_rejects_stale_and_invalid_signatures_before_upstream_contact(self) -> None:
        with patch.dict(os.environ, self.env, clear=True), patch(
            "app.api.routers.avatar.time.time", return_value=2_000.0
        ):
            config = self.client.get("/api/avatar/sdk-config").json()

        payload = {"config": {"walk_version": 3}}
        stale_timestamp = "1900"
        stale_token = _sdk_token(
            config["gatewayServer"], "POST", payload, config["appSecret"], stale_timestamp
        )
        with patch.dict(os.environ, self.env, clear=True), patch(
            "app.api.routers.avatar.time.time", return_value=2_000.0
        ):
            stale_response = self.client.post(
                config["gatewayServer"],
                json=payload,
                headers={
                    "X-APP-ID": config["appId"],
                    "X-TOKEN": stale_token,
                    "X-TIMESTAMP": stale_timestamp,
                },
            )
            invalid_response = self.client.post(
                config["gatewayServer"],
                json=payload,
                headers={
                    "X-APP-ID": config["appId"],
                    "X-TOKEN": "0" * 32,
                    "X-TIMESTAMP": "2000",
                },
            )

        self.assertEqual(stale_response.status_code, 401)
        self.assertEqual(stale_response.json()["error_code"], "AVATAR_GATEWAY_SIGNATURE_EXPIRED")
        self.assertEqual(invalid_response.status_code, 401)
        self.assertEqual(invalid_response.json()["error_code"], "AVATAR_GATEWAY_SIGNATURE_INVALID")

    def test_gateway_enforces_method_path_and_body_allowlists(self) -> None:
        with patch.dict(os.environ, self.env, clear=True):
            gateway = self.client.get("/api/avatar/sdk-config").json()["gatewayServer"]
            unexpected_body = self.client.post(gateway, json={"config": {}, "target_url": "https://example.test"})
            oversized_body = self.client.post(
                gateway,
                content=b'{"config":{"padding":"' + (b"x" * (64 * 1024)) + b'"}}',
                headers={"Content-Type": "application/json"},
            )
            query_variant = self.client.post(f"{gateway}?redirect=1", json={"config": {}})
            disallowed_method = self.client.put(gateway, json={"config": {}})

        self.assertEqual(unexpected_body.status_code, 400)
        self.assertEqual(oversized_body.status_code, 413)
        self.assertEqual(query_variant.status_code, 405)
        self.assertEqual(disallowed_method.status_code, 405)

    def test_gateway_grant_can_only_stop_its_bound_session_and_is_revoked_after_stop(self) -> None:
        env = {
            **self.env,
            "XINGYUAN_AVATAR_GRANT_TTL_SECONDS": "30",
            "XINGYUAN_AVATAR_ACTIVE_SESSION_TTL_SECONDS": "600",
        }
        upstream_methods: list[str] = []

        def upstream_handler(request: httpx.Request) -> httpx.Response:
            upstream_methods.append(request.method)
            if request.method == "POST":
                return httpx.Response(
                    200,
                    json={"data": {"session_id": "session-1", "resource_pack": {"name": "pack"}}},
                )
            return httpx.Response(200, json={"data": {"stopped": True}})

        real_async_client = httpx.AsyncClient
        transport = httpx.MockTransport(upstream_handler)
        with patch.dict(os.environ, env, clear=True), patch(
            "app.api.routers.avatar.time.time", return_value=3_000.0
        ):
            config = self.client.get("/api/avatar/sdk-config").json()
            start_payload = {"config": {"walk_version": 3}}
            start_token = _sdk_token(
                config["gatewayServer"], "POST", start_payload, config["appSecret"], "3000"
            )
            with patch(
                "app.api.routers.avatar.httpx.AsyncClient",
                side_effect=lambda *args, **kwargs: real_async_client(transport=transport),
            ):
                started = self.client.post(
                    config["gatewayServer"],
                    json=start_payload,
                    headers={
                        "X-APP-ID": config["appId"],
                        "X-TOKEN": start_token,
                        "X-TIMESTAMP": "3000",
                    },
                )
        self.assertEqual(started.status_code, 200)

        def delete_session(session_id: str) -> object:
            payload = {"session_id": session_id, "stop_reason": "user_stop"}
            token = _sdk_token(
                config["gatewayServer"], "DELETE", payload, config["appSecret"], "3040"
            )
            with patch.dict(os.environ, env, clear=True), patch(
                "app.api.routers.avatar.time.time", return_value=3_040.0
            ), patch(
                "app.api.routers.avatar.httpx.AsyncClient",
                side_effect=lambda *args, **kwargs: real_async_client(transport=transport),
            ):
                return self.client.request(
                    "DELETE",
                    config["gatewayServer"],
                    json=payload,
                    headers={
                        "X-APP-ID": config["appId"],
                        "X-TOKEN": token,
                        "X-TIMESTAMP": "3040",
                    },
                )

        wrong_session = delete_session("session-2")
        stopped = delete_session("session-1")
        replay = delete_session("session-1")

        self.assertEqual(wrong_session.status_code, 403)
        self.assertEqual(stopped.status_code, 200)
        self.assertEqual(replay.status_code, 401)
        self.assertEqual(upstream_methods, ["POST", "DELETE"])

    def test_active_gateway_grant_allows_bounded_vendor_reconnect_after_start_expiry(self) -> None:
        env = {
            **self.env,
            "XINGYUAN_AVATAR_GRANT_TTL_SECONDS": "30",
            "XINGYUAN_AVATAR_ACTIVE_SESSION_TTL_SECONDS": "600",
            "XINGYUAN_AVATAR_MAX_SESSION_STARTS_PER_GRANT": "2",
        }
        upstream_methods: list[str] = []
        session_number = 0

        def upstream_handler(request: httpx.Request) -> httpx.Response:
            nonlocal session_number
            upstream_methods.append(request.method)
            if request.method == "POST":
                session_number += 1
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "session_id": f"session-{session_number}",
                            "resource_pack": {"name": "pack"},
                        }
                    },
                )
            return httpx.Response(200, json={"data": {"stopped": True}})

        real_async_client = httpx.AsyncClient
        transport = httpx.MockTransport(upstream_handler)
        with patch.dict(os.environ, env, clear=True), patch(
            "app.api.routers.avatar.time.time", return_value=4_000.0
        ):
            config = self.client.get("/api/avatar/sdk-config").json()

        def start_session(timestamp: str) -> httpx.Response:
            payload = {"config": {"walk_version": 3}}
            token = _sdk_token(
                config["gatewayServer"], "POST", payload, config["appSecret"], timestamp
            )
            with patch.dict(os.environ, env, clear=True), patch(
                "app.api.routers.avatar.time.time", return_value=float(timestamp)
            ), patch(
                "app.api.routers.avatar.httpx.AsyncClient",
                side_effect=lambda *args, **kwargs: real_async_client(transport=transport),
            ):
                return self.client.post(
                    config["gatewayServer"],
                    json=payload,
                    headers={
                        "X-APP-ID": config["appId"],
                        "X-TOKEN": token,
                        "X-TIMESTAMP": timestamp,
                    },
                )

        first_start = start_session("4000")
        reconnect = start_session("4040")
        over_limit = start_session("4045")
        stop_payload = {"session_id": "session-2", "stop_reason": "user_stop"}
        stop_token = _sdk_token(
            config["gatewayServer"], "DELETE", stop_payload, config["appSecret"], "4050"
        )
        with patch.dict(os.environ, env, clear=True), patch(
            "app.api.routers.avatar.time.time", return_value=4_050.0
        ), patch(
            "app.api.routers.avatar.httpx.AsyncClient",
            side_effect=lambda *args, **kwargs: real_async_client(transport=transport),
        ):
            stopped = self.client.request(
                "DELETE",
                config["gatewayServer"],
                json=stop_payload,
                headers={
                    "X-APP-ID": config["appId"],
                    "X-TOKEN": stop_token,
                    "X-TIMESTAMP": "4050",
                },
            )

        self.assertEqual(first_start.status_code, 200)
        self.assertEqual(reconnect.status_code, 200)
        self.assertEqual(over_limit.status_code, 429)
        self.assertEqual(stopped.status_code, 200)
        self.assertEqual(upstream_methods, ["POST", "POST", "DELETE"])


if __name__ == "__main__":
    unittest.main()
