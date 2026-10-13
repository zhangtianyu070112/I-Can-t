from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app


class RoadshowRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_data_dir = settings.data_dir
        settings.data_dir = self.temp_dir.name
        self.frontend_dir = Path(self.temp_dir.name) / "frontend"
        self.frontend_dir.mkdir()
        (self.frontend_dir / "index.html").write_text("<html><body>roadshow app</body></html>", encoding="utf-8")
        self.previous_frontend_dist = os.environ.get("FRONTEND_DIST")
        os.environ["FRONTEND_DIST"] = str(self.frontend_dir)
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.client.close()
        settings.data_dir = self.original_data_dir
        if self.previous_frontend_dist is None:
            os.environ.pop("FRONTEND_DIST", None)
        else:
            os.environ["FRONTEND_DIST"] = self.previous_frontend_dist
        self.temp_dir.cleanup()

    def test_built_frontend_serves_client_routes_without_swallowing_api_errors(self) -> None:
        self.assertIn("roadshow app", self.client.get("/").text)
        self.assertIn("roadshow app", self.client.get("/profile").text)
        self.assertEqual(self.client.get("/api/does-not-exist").status_code, 404)
        self.assertEqual(self.client.get("/assets/missing.js").status_code, 404)

    def test_profile_timeout_returns_a_structured_error(self) -> None:
        with patch("app.api.routers.delivery.orchestrator.profile_chat", new=AsyncMock(side_effect=asyncio.TimeoutError)):
            response = self.client.post("/api/profile/extract", json={"student_id": "demo", "topic": "用例图"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["code"], "PROFILE_EXTRACT_TIMEOUT")
        self.assertTrue(payload["request_id"])

    def test_offline_profile_keeps_the_learner_topic_and_weak_point(self) -> None:
        with patch("app.agents.orchestrator.is_llm_configured", return_value=False):
            response = self.client.post("/api/profile/chat", json={
                "student_id": "roadshow-learner",
                "messages": [{"role": "user", "content": "我正在学习链表，尾插法更新尾指针容易出错，偏好执行轨迹图。"}],
            })
        self.assertTrue(response.json()["success"])
        evidence = response.json()["data"]["snapshot"]["evidence"]
        self.assertIn("链表", evidence["keywords"])
        self.assertIn("尾插法更新尾指针", evidence["weak_points"])
        persisted = self.client.get("/api/profile/roadshow-learner/overview").json()["data"]
        self.assertIn("尾插法更新尾指针", persisted["focus"]["weak_points"])

    def test_unavailable_generation_returns_an_api_error_instead_of_500(self) -> None:
        with patch("app.api.routers.delivery.orchestrator.generate", new=AsyncMock(side_effect=RuntimeError("模型尚未配置"))):
            response = self.client.post("/api/multimodal/generate", json={"student_id": "demo", "topic": "链表动画"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["success"])
        self.assertEqual(response.json()["error"]["code"], "MULTIMODAL_GENERATION_ERROR")


if __name__ == "__main__":
    unittest.main()
