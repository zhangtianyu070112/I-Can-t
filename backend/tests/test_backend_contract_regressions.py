from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.agents import Orchestrator
from app.api.routers.multimodal import _generate_code_case, _generate_video_items, _generate_voice_plan
from app.api.routers.ppt import PptOutlineRequest, _clean_outline
from app.api.routers.tutor import _with_legacy_tutor_fields
from app.core.config import settings
from app.db.sqlite import init_db
from app.main import create_app
from app.repo import get_user_events, read_json
from app.services.learning_state import _localize_profile_text, evaluation_overview, path_overview, profile_overview
from app.services.exercise_bank import _ability_radar, build_exercise_session, wrong_book_summary
from app.services.knowledge_hub import mastery_data


class BackendContractRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_settings = settings.model_dump()
        settings.data_dir = self.temp_dir.name
        for field in type(settings).model_fields:
            if field.endswith("_api_key"):
                setattr(settings, field, "")
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.client.close()
        for key, value in self.original_settings.items():
            setattr(settings, key, value)
        self.temp_dir.cleanup()

    def _route_matches(self, path: str, method: str) -> list:
        return [
            route
            for route in self.client.app.routes
            if getattr(route, "path", "") == path and method in (getattr(route, "methods", set()) or set())
        ]

    def test_canonical_routes_have_single_runtime_owner(self) -> None:
        expected = {
            ("/api/profile/chat", "POST"): "app.api.routers.profile",
            ("/api/path/plan", "POST"): "app.api.routers.path",
            ("/api/tutor/ask", "POST"): "app.api.routers.tutor",
            ("/api/resources", "GET"): "app.api.routers.resources",
        }

        for (path, method), module in expected.items():
            with self.subTest(path=path, method=method):
                matches = self._route_matches(path, method)
                self.assertEqual(len(matches), 1)
                self.assertEqual(matches[0].endpoint.__module__, module)

    def test_database_initialization_closes_its_connection(self) -> None:
        connection = MagicMock()
        with patch("app.db.sqlite.sqlite3.connect", return_value=connection):
            init_db()
        connection.close.assert_called_once_with()

    def test_cors_rejects_untrusted_origins_but_keeps_local_development(self) -> None:
        headers = {
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        }
        rejected = self.client.options(
            "/api/profile/chat",
            headers={**headers, "Origin": "https://evil.example"},
        )
        self.assertNotEqual(rejected.headers.get("access-control-allow-origin"), "https://evil.example")

        allowed = self.client.options(
            "/api/profile/chat",
            headers={**headers, "Origin": "http://127.0.0.1:5173"},
        )
        self.assertEqual(allowed.headers.get("access-control-allow-origin"), "http://127.0.0.1:5173")

    def test_profile_chat_persists_canonical_and_legacy_requests(self) -> None:
        student_id = "regression-profile"
        canonical = self.client.post(
            "/api/profile/chat",
            json={
                "student_id": student_id,
                "messages": [{"role": "user", "content": "我容易混淆用例图和需求访谈，偏好图解。"}],
                "major": "软件工程",
                "goals": "完成需求建模项目",
            },
        )
        self.assertEqual(canonical.status_code, 200)
        canonical_data = canonical.json()["data"]
        self.assertGreaterEqual(len(canonical_data["snapshot"]["dimensions"]), 6)

        legacy = self.client.post(
            "/api/profile/chat",
            json={"student_id": student_id, "question": "递归边界容易出错，希望分步讲解。"},
        )
        self.assertEqual(legacy.status_code, 200)
        legacy_data = legacy.json()["data"]
        self.assertIn("dimensions_updated", legacy_data["delta"])

        profile_file = Path(self.temp_dir.name) / "users" / student_id / "profiles.json"
        profiles = read_json(profile_file, [])
        self.assertEqual(len(profiles), 2)

        overview = self.client.get(f"/api/profile/{student_id}/overview").json()["data"]
        self.assertEqual(overview["learner"]["profile_version"], "v2.0")
        self.assertEqual(len(overview["history"]), 2)

    def test_path_plan_survives_a_fresh_overview_read(self) -> None:
        student_id = "regression-path"
        response = self.client.post(
            "/api/path/plan",
            json={"student_id": student_id, "goals": "掌握需求分析并完成项目建模"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        plan = data["plan"]
        self.assertGreater(len(plan["steps"]), 0)
        self.assertEqual(plan["analysis_mode"], "evidence_rules")
        self.assertEqual(len(data["path"]["nodes"]), len(plan["steps"]))

        overview = self.client.get(f"/api/path/overview?student_id={student_id}").json()["data"]
        self.assertTrue(overview["has_plan"])
        self.assertEqual(
            [node["title"] for node in overview["nodes"]],
            [node["title"] for node in data["path"]["nodes"]],
        )
        self.assertEqual(overview["strategy"], plan["strategy"])
        self.assertEqual(overview["rationale"], plan["rationale"])
        self.assertEqual(overview["rules"], plan["dynamic_rules"])

    def test_new_learner_overviews_do_not_invent_analysis_results(self) -> None:
        student_id = "regression-empty-learner"

        profile = profile_overview(student_id)
        path = path_overview(student_id)
        evaluation = evaluation_overview(student_id)

        self.assertEqual(profile["completeness"], 0)
        self.assertTrue(all(item["confidence"] == 0 for item in profile["dimensions"]))
        self.assertFalse(path["has_plan"])
        self.assertEqual(path["nodes"], [])
        self.assertEqual(path["stage_count"], 0)
        self.assertEqual(evaluation["evidence"]["total"], 0)
        self.assertEqual(evaluation["score"], 0)
        self.assertTrue(all(item["value"] == 0 for item in evaluation["dimensions"]))
        self.assertEqual(build_exercise_session(student_id)["questions"], [])
        self.assertEqual(build_exercise_session(student_id)["source"], "no_generated_question_bank")
        self.assertTrue(all(item["score"] == 0 for item in wrong_book_summary(student_id)["ability_radar"]))
        mastery = mastery_data(student_id)
        self.assertEqual(mastery["summary"]["assessed_nodes"], 0)
        self.assertEqual(mastery["summary"]["average_mastery"], 0)
        self.assertTrue(all(item["mastery"] == 0 for item in mastery["nodes"]))
        self.assertTrue(all(item["evidence_count"] == 0 for item in mastery["nodes"]))

    def test_ability_radar_uses_overall_evidence_when_transfer_tags_are_missing(self) -> None:
        radar = _ability_radar(
            [
                {"type": "single_choice", "tags": ["基础知识"], "stem": "基础概念题", "correct": True},
                {"type": "single_choice", "tags": ["基础知识"], "stem": "基础判断题", "correct": False},
            ]
        )
        transfer = next(item for item in radar if item["name"] == "应用迁移能力")
        self.assertGreater(transfer["score"], 0)
        self.assertEqual(transfer["basis"], "综合答题表现推断")

    def test_profile_model_phrases_are_localized_before_reaching_pages(self) -> None:
        samples = {
            "beginner to intermediate": "初学到中等水平",
            "self-introduction confusion": "自我介绍相关概念易混淆",
            "text with examples": "文字讲解结合实例",
            "external guidance + achievement-oriented": "外部指导与成就目标驱动型",
        }
        for source, expected in samples.items():
            with self.subTest(source=source):
                self.assertEqual(_localize_profile_text(source), expected)

    def test_analysis_endpoints_require_an_explicit_learner(self) -> None:
        for path in [
            "/api/dashboard/overview",
            "/api/profile/current",
            "/api/workshop/overview",
            "/api/path/overview",
            "/api/evaluate/overview",
            "/api/knowledge/graph",
        ]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 422)

    def test_short_model_path_is_not_padded_with_synthetic_stages(self) -> None:
        student_id = "regression-short-model-path"
        client = MagicMock()
        client.chat_json = AsyncMock(
            return_value={
                "title": "模型只返回两步",
                "steps": [
                    {"order": 1, "objective": "诊断", "resources": [], "assessment": "完成诊断"},
                    {"order": 2, "objective": "练习", "resources": [], "assessment": "完成练习"},
                ],
            }
        )
        with patch("app.agents.orchestrator.is_llm_configured", return_value=True), patch(
            "app.agents.orchestrator.get_llm_client_for", return_value=client
        ):
            result = asyncio.run(Orchestrator().plan_path(student_id=student_id, goals="掌握链表"))

        self.assertEqual(len(result["plan"]["steps"]), 2)
        self.assertEqual(len(path_overview(student_id)["nodes"]), 2)

    def test_resource_generation_only_runs_requested_agents(self) -> None:
        student_id = "regression-selected-resource-types"
        generate_one = AsyncMock(return_value='{"meta": {}, "questions": []}')
        quality_check = AsyncMock(return_value=None)
        with patch.object(Orchestrator, "_generate_one", generate_one), patch.object(
            Orchestrator, "_run_quality_check", quality_check
        ):
            resources = asyncio.run(
                Orchestrator().generate(
                    student_id=student_id,
                    requirement={
                        "course": "数据结构",
                        "chapter": "链表",
                        "resource_types": ["question_bank"],
                        "weak_points": ["指针更新"],
                    },
                )
            )

        self.assertEqual(generate_one.await_count, 1)
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["type"], "question_bank")

    def test_evaluation_report_survives_overview_and_legacy_reads(self) -> None:
        student_id = "regression-evaluate"
        response = self.client.post("/api/evaluate/report", json={"student_id": student_id})
        self.assertEqual(response.status_code, 200)
        report = response.json()["data"]["report"]

        overview = self.client.get(f"/api/evaluate/overview?student_id={student_id}").json()["data"]
        self.assertEqual(overview["latest_report"], report)

        legacy = self.client.get(f"/api/evaluation/report?student_id={student_id}").json()["data"]
        self.assertEqual(legacy, report)

    def test_tutor_legacy_request_uses_real_orchestrator_and_persists(self) -> None:
        student_id = "regression-tutor"
        client = MagicMock()
        client.chat_text = AsyncMock(return_value="基于课程证据的模型回答")
        with patch("app.agents.orchestrator.is_llm_configured", return_value=True), patch(
            "app.agents.orchestrator.get_llm_client_for", return_value=client
        ):
            response = self.client.post(
                "/api/tutor/ask",
                json={"student_id": student_id, "query": "请分步解释用例图和需求访谈的区别"},
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertTrue(data.get("answer"))
        self.assertTrue(data.get("markdown"))
        self.assertIn("knowledge_base_hit", data)
        self.assertTrue(any(item.get("event_type") == "tutor" for item in get_user_events(student_id)))

    def test_tutor_upstream_timeout_returns_no_synthetic_answer_or_evidence(self) -> None:
        student_id = "regression-tutor-timeout"
        client = MagicMock()
        client.chat_text = AsyncMock(side_effect=TimeoutError("upstream stalled"))
        with patch("app.agents.orchestrator.is_llm_configured", return_value=True), patch(
            "app.agents.orchestrator.get_llm_client_for", return_value=client
        ):
            with self.assertRaisesRegex(RuntimeError, "没有生成回答"):
                asyncio.run(
                    Orchestrator().tutor_ask(
                        student_id=student_id,
                        question="请解释链表插入",
                        context={},
                    )
                )
        self.assertFalse(any(item.get("event_type") == "tutor" for item in get_user_events(student_id)))

    def test_resource_generation_without_model_returns_no_template_resource(self) -> None:
        with patch("app.agents.orchestrator.is_llm_configured", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "没有生成模板资源"):
                asyncio.run(
                    Orchestrator().generate(
                        student_id="regression-no-resource-fallback",
                        requirement={"course": "数据结构", "resource_types": ["question_bank"]},
                    )
                )

    def test_multimodal_generation_without_model_returns_no_template_content(self) -> None:
        with patch("app.api.routers.multimodal.is_llm_configured", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "没有生成固定推荐项"):
                asyncio.run(_generate_video_items("链表"))
            with self.assertRaisesRegex(RuntimeError, "没有生成模板案例"):
                asyncio.run(_generate_code_case("链表", "Python"))
            with self.assertRaisesRegex(RuntimeError, "没有生成模板脚本"):
                asyncio.run(_generate_voice_plan("链表", "general"))

    def test_multimodal_generation_timeout_returns_no_template_content(self) -> None:
        client = MagicMock()
        client.chat_json = AsyncMock(side_effect=TimeoutError("video model stalled"))
        client.chat_text = AsyncMock(side_effect=TimeoutError("text model stalled"))

        with patch("app.api.routers.multimodal.is_llm_configured", return_value=True), patch(
            "app.api.routers.multimodal.get_llm_client_for", return_value=client
        ):
            with self.assertRaisesRegex(RuntimeError, "没有生成固定推荐项"):
                asyncio.run(_generate_video_items("链表"))
            with self.assertRaisesRegex(RuntimeError, "没有生成模板案例"):
                asyncio.run(_generate_code_case("链表", "Python"))
            with self.assertRaisesRegex(RuntimeError, "没有生成模板脚本"):
                asyncio.run(_generate_voice_plan("链表", "general"))

    def test_ppt_generation_requires_a_real_generated_outline(self) -> None:
        with patch(
            "app.api.routers.ppt._prepare_ai_ppt_backgrounds",
            new=AsyncMock(side_effect=AssertionError("missing outline must stop before asset generation")),
        ), patch("app.api.routers.ppt._create_designed_pptx"):
            response = self.client.post(
                "/api/ppt/generate-from-outline",
                json={"student_id": "regression-ppt", "topic": "链表边界条件", "requirements": "讲解头插法"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertIn("大纲", payload["error"])

    def test_generated_local_image_can_be_exported(self) -> None:
        image_dir = settings.files_path / "generated" / "images"
        image_dir.mkdir(parents=True, exist_ok=True)
        image_path = image_dir / "课堂插图.png"
        image_path.write_bytes(b"\x89PNG\r\n\x1a\nregression-image")

        response = self.client.post(
            "/api/export/image",
            json={
                "image_url": "/files/generated/images/课堂插图.png",
                "title": "课堂插图",
                "file_name": "课堂插图.png",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, image_path.read_bytes())
        self.assertIn("attachment", response.headers.get("content-disposition", ""))

    def test_ppt_still_exports_when_glm_backgrounds_fail(self) -> None:
        outline = {
            "title": "链表边界条件",
            "subtitle": "课堂讲解",
            "slides": [
                {"title": "问题导入", "body": "从空链表和单节点链表出发，观察头插与尾插时指针关系的变化。"},
                {"title": "核心步骤", "body": "先保存后继节点，再修改当前节点指向，最后更新头指针并检查边界条件。"},
                {"title": "迁移练习", "body": "将同样的边界检查方法迁移到删除、反转和合并链表的任务中。"},
            ],
        }
        with patch("app.api.routers.ppt._image_api_key", return_value="regression-key"), patch(
            "app.api.routers.ppt._generate_glm_image_file", new=AsyncMock(return_value=False)
        ):
            response = self.client.post(
                "/api/ppt/generate-from-outline",
                json={"topic": "链表边界条件", "requirements": "讲解边界条件", "slide_count": 3, "outline": outline},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertTrue(payload["image_generation_warning"])
        self.assertTrue((settings.files_path / "generated" / "ppt" / payload["filename"]).is_file())

    def test_invalid_model_outline_is_not_replaced_with_template_slides(self) -> None:
        request = PptOutlineRequest(topic="链表边界条件", requirements="讲解头插法", slide_count=6)
        with self.assertRaisesRegex(ValueError, "有效幻灯片"):
            _clean_outline({"title": "链表边界条件", "slides": [{"title": "只有标题"}]}, request)

    def test_tutor_does_not_treat_low_relevance_candidates_as_knowledge_evidence(self) -> None:
        data = _with_legacy_tutor_fields(
            {
                "answer": {
                    "text": "候选片段与问题并不相关。",
                    "references": [{"title": "链表动画", "score": 0.09}],
                }
            }
        )
        self.assertFalse(data["knowledge_base_hit"])
        self.assertIn("未检索到可引用证据", data["markdown"])


if __name__ == "__main__":
    unittest.main()
