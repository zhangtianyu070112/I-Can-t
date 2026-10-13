from __future__ import annotations

import asyncio
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.api.routers import path as path_router
from app.core.config import settings
from app.repo import insert_learning_event
from app.schemas import PathStageQuestionRequest
from app.services.learning_state import path_overview
from app.services.path_progress import add_path_branch, register_stage_question_bank, record_stage_answer


class PathProgressTest(unittest.TestCase):
    def setUp(self):
        self.previous_data_dir = settings.data_dir
        self.data_dir = Path(tempfile.mkdtemp(prefix="path-progress-test-"))
        settings.data_dir = str(self.data_dir)
        insert_learning_event(
            "learner",
            "path_plan",
            {
                "title": "测试路径",
                "path": {
                    "title": "测试路径",
                    "steps": [
                        {"order": 1, "objective": "阶段一", "resources": ["question_bank"]},
                        {"order": 2, "objective": "阶段二", "resources": ["question_bank"]},
                    ],
                },
            },
        )

    def tearDown(self):
        settings.data_dir = self.previous_data_dir
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_answers_update_mastery_and_unlock_next_stage(self):
        register_stage_question_bank(
            "learner",
            stage_id="stage-1",
            resource_id="bank-1",
            target_count=5,
        )

        result = None
        for index, correct in enumerate([True, True, True, True, False]):
            result = record_stage_answer(
                "learner",
                stage_id="stage-1",
                question_id=f"question-{index}",
                correct=correct,
                target_count=5,
                resource_id="bank-1",
            )

        self.assertIsNotNone(result)
        self.assertEqual(result["mastery"], 80)
        self.assertTrue(result["advanced"])
        overview = path_overview("learner")
        self.assertEqual(overview["nodes"][0]["status"], "completed")
        self.assertEqual(overview["current_stage"]["id"], "stage-2")

    def test_incomplete_score_keeps_current_stage_in_reinforcement(self):
        register_stage_question_bank(
            "learner",
            stage_id="stage-1",
            resource_id="bank-1",
            target_count=5,
        )

        result = None
        for index, correct in enumerate([True, True, True, False, False]):
            result = record_stage_answer(
                "learner",
                stage_id="stage-1",
                question_id=f"question-{index}",
                correct=correct,
                target_count=5,
                resource_id="bank-1",
            )

        self.assertEqual(result["mastery"], 60)
        self.assertFalse(result["advanced"])
        self.assertEqual(result["status"], "warning")
        self.assertEqual(path_overview("learner")["current_stage"]["id"], "stage-1")

    def test_knowledge_branch_is_attached_to_current_stage_and_deduplicated(self):
        first = add_path_branch(
            "learner",
            knowledge_node_id="knowledge-java-io",
            title="Java I/O",
            description="补充分支学习",
            mastery=35,
        )
        second = add_path_branch(
            "learner",
            knowledge_node_id="knowledge-java-io",
            title="Java I/O",
            mastery=35,
        )

        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["branch"]["parent_id"], "stage-1")
        overview = path_overview("learner")
        self.assertEqual(len(overview["branches"]), 1)
        self.assertEqual(overview["nodes"][0]["branches"][0]["knowledge_node_id"], "knowledge-java-io")

    def test_knowledge_node_generation_calls_model_with_selected_topic(self):
        generated_bank = {"id": "knowledge-bank-1", "type": "question_bank", "content_uri": ""}
        with patch.object(path_router.orchestrator, "generate", new=AsyncMock(return_value=[generated_bank])) as generate:
            response = asyncio.run(
                path_router.generate_stage_questions(
                    PathStageQuestionRequest(
                        student_id="learner",
                        stage_id="stage-1",
                        knowledge_node_id="knowledge-java-io",
                        topic="Java I/O",
                        topic_description="文件与对象流",
                        count=4,
                    )
                )
            )

        self.assertTrue(response.success)
        requirement = generate.await_args.kwargs["requirement"]
        self.assertEqual(requirement["specific_knowledge_point"], "Java I/O")
        self.assertEqual(requirement["constraints"]["knowledge_node_id"], "knowledge-java-io")
        self.assertEqual(response.data["question_bank"]["id"], "knowledge-bank-1")


if __name__ == "__main__":
    unittest.main()
