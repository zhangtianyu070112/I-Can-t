from __future__ import annotations

from fastapi import APIRouter

from app.core.ids import new_id
from app.evolution import EvolutionEngine
from app.repo import get_latest_profile_snapshot, get_user_usages, insert_learning_event, insert_resource_usage, list_resources
from app.schemas import ApiResponse, PushFeedbackRequest, PushRemoveRequest
from app.services.knowledge_hub import mastery_data


router = APIRouter(prefix="/api/push", tags=["push"])
evolution_engine = EvolutionEngine()


@router.get("/feed", response_model=ApiResponse)
async def feed(student_id: str) -> ApiResponse:
    request_id = new_id()
    resources = list_resources(student_id)
    profile = get_latest_profile_snapshot(student_id) or {}
    usages = get_user_usages(student_id)
    weak_points = (profile.get("evidence") or {}).get("weak_points", [])
    mastery = mastery_data(student_id)
    weak_mastery_names = [
        n.get("name", "")
        for n in mastery.get("nodes", [])
        if float(n.get("current_mastery", 0)) < 60
    ]
    weak_text = " ".join(str(x) for x in weak_points) + " " + str(profile.get("mistake_patterns", ""))
    weak_text += " " + " ".join(str(x) for x in weak_mastery_names)
    usage_by_resource = {u.get("resource_id"): u for u in usages}

    items = []
    for r in resources:
        usage = usage_by_resource.get(r.get("id"))
        if usage and str(usage.get("action", "")).lower() in {"removed", "deleted", "dismissed"}:
            continue
        score = 50
        r_type = r.get("type", "")
        tags = r.get("tags", []) or []
        if r_type in ["question_bank", "lecture_doc", "mindmap"]:
            score += 12
        if r_type in ["practice_case", "video_script", "reading"]:
            score += 8
        if any(str(tag) and str(tag) in weak_text for tag in tags):
            score += 20
        if usage and usage.get("action") == "like":
            score += 10
        if usage and usage.get("action") == "dislike":
            score -= 25

        reason = _push_reason(r_type, tags, weak_points, weak_mastery_names)
        items.append(
            {
                "resource_id": r["id"],
                "title": r["title"],
                "type": r_type,
                "tags": tags,
                "reason": reason,
                "recommend_score": score,
                "use_timing": _use_timing(r_type),
                "download_url": f"/{r['content_uri']}",
                "created_at": r["created_at"],
            }
        )
    items.sort(key=lambda x: (x["recommend_score"], x["created_at"]), reverse=True)
    return ApiResponse(request_id=request_id, success=True, data={"items": items})


@router.post("/remove", response_model=ApiResponse)
async def remove_from_feed(req: PushRemoveRequest) -> ApiResponse:
    request_id = new_id()
    try:
        resource = next((item for item in list_resources(req.student_id) if item.get("id") == req.resource_id), None)
        if resource is None:
            return ApiResponse(
                request_id=request_id,
                success=False,
                error={"code": "PUSH_RESOURCE_NOT_FOUND", "message": "该推送资源不存在或已被移除"},
            )
        insert_resource_usage(
            student_id=req.student_id,
            resource_id=req.resource_id,
            action="removed",
            duration_sec=None,
            feedback={"scope": "push_feed"},
        )
        insert_learning_event(
            req.student_id,
            "push_resource_removed",
            {"resource_id": req.resource_id, "resource_title": resource.get("title", "")},
        )
        return ApiResponse(
            request_id=request_id,
            success=True,
            data={"ok": True, "resource_id": req.resource_id, "resource_preserved": True},
        )
    except Exception as e:
        return ApiResponse(request_id=request_id, success=False, error={"code": "PUSH_REMOVE_ERROR", "message": str(e)})


@router.post("/feedback", response_model=ApiResponse)
async def feedback(req: PushFeedbackRequest) -> ApiResponse:
    request_id = new_id()
    try:
        insert_resource_usage(
            student_id=req.student_id, resource_id=req.resource_id, action=req.action, duration_sec=None, feedback=req.feedback
        )
        insert_learning_event(req.student_id, "push_feedback", {"resource_id": req.resource_id, "action": req.action})
        evolution_result = None
        if req.action.lower() in {"dislike", "negative", "too_hard", "not_match"}:
            resource = next((r for r in list_resources(req.student_id) if r.get("id") == req.resource_id), {})
            evolution_result = await evolution_engine.evaluate_and_evolve(
                student_id=req.student_id,
                trigger_event="negative_feedback",
                context_data={
                    "resource_id": req.resource_id,
                    "action": req.action,
                    "resource_type": resource.get("type", ""),
                    "resource_title": resource.get("title", ""),
                    "feedback": req.feedback,
                },
            )
        return ApiResponse(request_id=request_id, success=True, data={"ok": True, "evolution": evolution_result})
    except Exception as e:
        return ApiResponse(request_id=request_id, success=False, error={"code": "PUSH_FEEDBACK_ERROR", "message": str(e)})


def _push_reason(resource_type: str, tags: list, weak_points: list, weak_mastery_names: list[str] | None = None) -> str:
    if weak_points and tags:
        matched = [str(t) for t in tags if any(str(t) in str(w) or str(w) in str(t) for w in weak_points)]
        if matched:
            return f"匹配你的薄弱点：{'、'.join(matched[:3])}"
    if weak_mastery_names:
        return f"结合知识图谱低掌握节点推荐：{'、'.join(weak_mastery_names[:2])}"
    mapping = {
        "lecture_doc": "用于建立课程概念框架，适合阶段学习开始前阅读",
        "mindmap": "用于快速梳理知识结构，适合复习和查漏补缺",
        "question_bank": "用于诊断掌握情况，适合阶段学习后检测",
        "reading": "用于拓展理解和项目迁移，适合基础掌握后阅读",
        "practice_case": "用于把知识转化为实操产出，适合综合训练",
        "video_script": "用于多模态图解复盘，适合概念混淆时观看或制作视频",
        "quality_check": "用于检查生成资源的事实风险和结构完整性",
    }
    return mapping.get(resource_type, "根据你的画像、学习进度和近期生成内容推荐")


def _use_timing(resource_type: str) -> str:
    mapping = {
        "lecture_doc": "学习阶段开始前",
        "mindmap": "概念复习或考前梳理时",
        "question_bank": "阶段学习结束后",
        "reading": "完成基础学习后",
        "practice_case": "进入项目实操阶段时",
        "video_script": "图形化讲解或短视频复盘时",
        "quality_check": "资源提交或展示前",
    }
    return mapping.get(resource_type, "根据学习状态动态推送")

