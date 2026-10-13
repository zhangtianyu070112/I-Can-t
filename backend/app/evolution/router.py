from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.streaming import stream_operation, stream_response
from app.core.ids import new_id
from app.evolution.engine import EvolutionEngine
from app.schemas import ApiResponse


router = APIRouter(prefix="/api/evolution", tags=["evolution"])
engine = EvolutionEngine()


class EvolveRequest(BaseModel):
    student_id: str
    trigger_event: str
    context_data: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False
    preview_decision: dict[str, Any] | None = None


@router.post("/trigger", response_model=ApiResponse)
async def trigger_evolution(req: EvolveRequest) -> ApiResponse:
    request_id = new_id()
    try:
        result = await engine.evaluate_and_evolve(
            student_id=req.student_id,
            trigger_event=req.trigger_event,
            context_data=req.context_data,
            dry_run=req.dry_run,
            decision_override=req.preview_decision,
        )
        return ApiResponse(request_id=request_id, success=True, data=result)
    except Exception as e:
        return ApiResponse(request_id=request_id, success=False, error={"code": "EVOLUTION_ERROR", "message": str(e)})


@router.post("/trigger/stream")
async def trigger_evolution_stream(req: EvolveRequest):
    request_id = new_id()

    async def work():
        return await engine.evaluate_and_evolve(
            student_id=req.student_id,
            trigger_event=req.trigger_event,
            context_data=req.context_data,
            dry_run=req.dry_run,
            decision_override=req.preview_decision,
        )

    def text(result: dict) -> str:
        parts = [
            str(result.get("reason", "") or result.get("rationale", "")),
            str(result.get("mode", "")),
        ]
        actions = result.get("actions") or result.get("recommended_actions") or result.get("decision", {}).get("actions", [])
        if isinstance(actions, list):
            parts.extend(str(x) for x in actions)
        return "\n".join([p for p in parts if p])

    return stream_response(
        stream_operation(
            request_id=request_id,
            work=work,
            start_message="开始判断是否需要画像进化",
            final_key="result",
            chunk_text=text,
            chunk_path="evolution_text",
        )
    )
