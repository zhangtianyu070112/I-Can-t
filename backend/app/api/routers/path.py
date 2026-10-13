from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.streaming import stream_live_operation, stream_response
from app.agents import Orchestrator
from app.core.config import settings
from app.core.ids import new_id
from app.schemas import ApiResponse, PathBranchRequest, PathPlanRequest, PathStageQuestionRequest
from app.services.learning_state import path_overview
from app.services.path_progress import add_path_branch, register_stage_question_bank
from app.services.resource_structure import extract_questions_json


router = APIRouter(prefix="/api/path", tags=["path"])
orchestrator = Orchestrator()


@router.get("/overview", response_model=ApiResponse)
async def overview(student_id: str = Query(..., min_length=1)) -> ApiResponse:
    request_id = new_id()
    try:
        return ApiResponse(request_id=request_id, success=True, data=path_overview(student_id))
    except Exception as e:
        return ApiResponse(
            request_id=request_id,
            success=False,
            error={"code": "PATH_OVERVIEW_ERROR", "message": str(e)},
        )


@router.post("/branch", response_model=ApiResponse)
async def create_branch(req: PathBranchRequest) -> ApiResponse:
    request_id = new_id()
    try:
        result = add_path_branch(
            req.student_id,
            knowledge_node_id=req.knowledge_node_id,
            title=req.title,
            description=req.description,
            mastery=req.mastery,
        )
        return ApiResponse(
            request_id=request_id,
            success=True,
            data={**result, "path": path_overview(req.student_id)},
        )
    except Exception as e:
        return ApiResponse(
            request_id=request_id,
            success=False,
            error={"code": "PATH_BRANCH_ERROR", "message": str(e)},
        )


@router.post("/stage/questions", response_model=ApiResponse)
async def generate_stage_questions(req: PathStageQuestionRequest) -> ApiResponse:
    request_id = new_id()
    try:
        overview_data = path_overview(req.student_id)
        nodes = overview_data.get("nodes") if isinstance(overview_data.get("nodes"), list) else []
        current = overview_data.get("current_stage") if isinstance(overview_data.get("current_stage"), dict) else {}
        stage_id = str(req.stage_id or current.get("id") or "")
        stage = next((item for item in nodes if str(item.get("id") or "") == stage_id), None)
        if not stage:
            raise ValueError("请先生成学习路径，再定制阶段题库。")
        if stage.get("status") == "locked":
            raise ValueError("该阶段尚未解锁，请先完成当前学习阶段。")

        allowed_types = {
            "single_choice", "multiple_choice", "true_false", "blank", "short_answer",
            "case_analysis", "calculation", "matching", "ordering",
        }
        question_types = [item for item in req.question_types if item in allowed_types]
        if not question_types:
            question_types = ["single_choice"]
        type_counts = {
            key: max(0, min(20, int(value or 0)))
            for key, value in req.type_counts.items()
            if key in question_types and int(value or 0) > 0
        }
        configured_count = sum(type_counts.values()) if type_counts else req.count
        configured_count = max(1, min(50, configured_count))
        topic_title = str(req.topic or stage.get("title") or f"学习阶段 {stage.get('step') or ''}").strip()
        topic_description = str(
            req.topic_description or stage.get("goal") or stage.get("checkpoint") or ""
        ).strip()
        requirement = {
            "course": overview_data.get("title") or "个性化学习路径",
            "chapter": stage.get("title") or f"学习阶段 {stage.get('step') or ''}",
            "specific_knowledge_point": topic_title,
            "knowledge_points": topic_description,
            "goals": "\n".join(
                item for item in [
                    topic_description,
                    str(stage.get("goal") or ""),
                    str(stage.get("checkpoint") or ""),
                ] if item
            ),
            "weak_points": [topic_title],
            "special_requirements": f"题目必须围绕“{topic_title}”生成，并与当前路径阶段保持一致，不得混入其它章节内容。",
            "resource_types": ["question_bank"],
            "preferred_resources": ["question_bank"],
            "constraints": {
                "source": "path_stage_quiz",
                "difficulty": req.difficulty,
                "path_stage_id": stage_id,
                "path_stage_title": stage.get("title") or "",
                "knowledge_node_id": req.knowledge_node_id or "",
                "knowledge_node_title": topic_title,
                "skip_quality_check": True,
            },
            "question_config": {
                "count": configured_count,
                "difficulty": req.difficulty,
                "types": list(type_counts) if type_counts else question_types,
                "type_counts": type_counts,
            },
        }
        async def collect_model_chunk(_: str) -> None:
            return None

        resources = await orchestrator.generate(
            student_id=req.student_id,
            requirement=requirement,
            on_chunk=collect_model_chunk,
        )
        question_bank = next((item for item in resources if item.get("type") == "question_bank"), None)
        if not question_bank:
            raise RuntimeError("题库模型没有返回可用题库。")
        actual_count = _question_count(question_bank) or configured_count
        stage_progress = register_stage_question_bank(
            req.student_id,
            stage_id=stage_id,
            resource_id=str(question_bank.get("id") or ""),
            target_count=actual_count,
        )
        refreshed = path_overview(req.student_id)
        refreshed_stage = next(
            (item for item in refreshed.get("nodes", []) if str(item.get("id") or "") == stage_id),
            stage,
        )
        return ApiResponse(
            request_id=request_id,
            success=True,
            data={
                "stage": refreshed_stage,
                "question_bank": question_bank,
                "resources": resources,
                "progress": stage_progress,
            },
        )
    except Exception as e:
        return ApiResponse(
            request_id=request_id,
            success=False,
            error={"code": "PATH_STAGE_QUESTION_ERROR", "message": str(e)},
        )


@router.post("/plan", response_model=ApiResponse)
async def plan(req: PathPlanRequest) -> ApiResponse:
    request_id = new_id()
    try:
        result = await orchestrator.plan_path(student_id=req.student_id, goals=req.goals)
        return ApiResponse(
            request_id=request_id,
            success=True,
            data=_with_compatibility_fields(result, student_id=req.student_id),
        )
    except Exception as e:
        return ApiResponse(request_id=request_id, success=False, error={"code": "PATH_PLAN_ERROR", "message": str(e)})


@router.post("/plan/stream")
async def plan_stream(req: PathPlanRequest):
    request_id = new_id()

    async def work(on_chunk):
        result = await orchestrator.plan_path(student_id=req.student_id, goals=req.goals, on_chunk=on_chunk)
        return _with_compatibility_fields(result, student_id=req.student_id)

    def text(result: dict) -> str:
        plan = result.get("plan", result)
        parts = [str(plan.get("title", "")), str(plan.get("rationale", ""))]
        for step in plan.get("steps", []) or []:
            parts.append(f"{step.get('order', '')}. {step.get('objective', '')} {step.get('assessment', '')}")
        return "\n".join([p for p in parts if p])

    return stream_response(
        stream_live_operation(
            request_id=request_id,
            work=work,
            start_message="开始规划个性化学习路径",
            final_key="result",
            fallback_text=text,
            chunk_path="plan_text",
        )
    )


def _with_compatibility_fields(result: dict, *, student_id: str) -> dict:
    data = dict(result or {})
    raw_plan = data.get("plan") if isinstance(data.get("plan"), dict) else data
    plan_data = dict(raw_plan or {})
    nodes = _normalize_nodes(plan_data.get("nodes") or plan_data.get("steps") or [])
    path_data = dict(data.get("path") or {})
    path_data.update(
        {
            "title": plan_data.get("title") or path_data.get("title") or "个性化学习路径",
            "nodes": nodes,
        }
    )
    data.update(
        {
            "student_id": student_id,
            "title": path_data["title"],
            "plan": plan_data,
            "path": path_data,
        }
    )
    return data


def _normalize_nodes(raw_nodes: object) -> list[dict]:
    if not isinstance(raw_nodes, list):
        return []
    nodes: list[dict] = []
    for index, raw in enumerate(raw_nodes):
        if not isinstance(raw, dict):
            continue
        step = raw.get("step") or raw.get("order") or index + 1
        title = raw.get("title") or raw.get("objective") or f"学习阶段 {step}"
        nodes.append(
            {
                **raw,
                "id": raw.get("id") or f"stage-{step}",
                "step": step,
                "title": title,
                "goal": raw.get("goal") or raw.get("objective") or "",
                "resources": raw.get("resources") if isinstance(raw.get("resources"), list) else [],
                "tasks": raw.get("tasks") if isinstance(raw.get("tasks"), list) else [],
                "checkpoint": raw.get("checkpoint") or raw.get("assessment") or "",
                "status": raw.get("status") or ("current" if not nodes else "locked"),
            }
        )
    return nodes


def _question_count(resource: dict) -> int:
    try:
        path = settings.data_path / str(resource.get("content_uri") or "")
        payload = extract_questions_json(path.read_text(encoding="utf-8"))
        questions = payload.get("questions") if isinstance(payload, dict) else payload
        return len(questions) if isinstance(questions, list) else 0
    except Exception:
        return 0

