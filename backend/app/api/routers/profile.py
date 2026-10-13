from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.agents import Orchestrator
from app.core.ids import new_id
from app.api.streaming import stream_live_operation, stream_response
from app.repo import get_latest_profile_snapshot
from app.schemas import ApiResponse, ProfileChatRequest
from app.services.learning_state import profile_overview


router = APIRouter(prefix="/api/profile", tags=["profile"])
orchestrator = Orchestrator()

PROFILE_DIMENSION_KEYS = [
    "knowledge_base_level",
    "cognitive_style",
    "mistake_patterns",
    "modality_preference",
    "pace_preference",
    "motivation_style",
]


def _normalized_messages(req: ProfileChatRequest) -> list[dict[str, str]]:
    messages = [message.model_dump() for message in req.messages]
    if messages:
        return messages
    legacy_text = req.question or req.query or req.topic or req.goals or "请根据已有学习证据更新用户画像"
    return [{"role": "user", "content": legacy_text}]


def _with_compatibility_fields(result: dict) -> dict:
    data = dict(result or {})
    snapshot = dict(data.get("snapshot") or {})
    dimensions = {key: str(snapshot.get(key) or "") for key in PROFILE_DIMENSION_KEYS}
    weaknesses = list((snapshot.get("evidence") or {}).get("weak_points") or [])
    snapshot.setdefault("dimensions", dimensions)
    snapshot.setdefault("weaknesses", weaknesses)

    delta = dict(data.get("delta") or {})
    changed = [key for key in PROFILE_DIMENSION_KEYS if key in delta]
    delta.setdefault("dimensions_updated", changed or list(dimensions))
    delta.setdefault("weaknesses", weaknesses)

    data["snapshot"] = snapshot
    data["delta"] = delta
    return data


@router.post("/chat", response_model=ApiResponse)
async def profile_chat(req: ProfileChatRequest) -> ApiResponse:
    request_id = new_id()
    try:
        result = await orchestrator.profile_chat(
            student_id=req.student_id,
            messages=_normalized_messages(req),
            major=req.major,
            goals=req.goals,
        )
        return ApiResponse(request_id=request_id, success=True, data=_with_compatibility_fields(result))
    except Exception as e:
        return ApiResponse(
            request_id=request_id, success=False, error={"code": "PROFILE_CHAT_ERROR", "message": str(e)}
        )


@router.post("/chat/stream")
async def profile_chat_stream(req: ProfileChatRequest):
    request_id = new_id()

    async def work(on_chunk):
        result = await orchestrator.profile_chat(
            student_id=req.student_id,
            messages=_normalized_messages(req),
            major=req.major,
            goals=req.goals,
            on_chunk=on_chunk,
        )
        return _with_compatibility_fields(result)

    return stream_response(
        stream_live_operation(
            request_id=request_id,
            work=work,
            start_message="开始分析学习画像",
            final_key="result",
            fallback_text=lambda result: str(result.get("rationale", "")),
            chunk_path="rationale",
        )
    )


@router.get("/{student_id}/overview", response_model=ApiResponse)
async def get_profile_overview(student_id: str) -> ApiResponse:
    request_id = new_id()
    try:
        return ApiResponse(request_id=request_id, success=True, data=profile_overview(student_id))
    except Exception as e:
        return ApiResponse(
            request_id=request_id,
            success=False,
            error={"code": "PROFILE_OVERVIEW_ERROR", "message": str(e)},
        )


@router.get("/{student_id}", response_model=ApiResponse)
async def get_profile(student_id: str) -> ApiResponse:
    request_id = new_id()
    snap = get_latest_profile_snapshot(student_id)
    if not snap:
        raise HTTPException(status_code=404, detail="profile_not_found")
    return ApiResponse(request_id=request_id, success=True, data={"snapshot": snap})

