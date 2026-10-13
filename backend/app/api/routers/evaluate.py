from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.streaming import stream_live_operation, stream_response
from app.agents import Orchestrator
from app.core.ids import new_id
from app.schemas import ApiResponse, EvaluateReportRequest
from app.services.learning_state import evaluation_overview


router = APIRouter(prefix="/api/evaluate", tags=["evaluate"])
orchestrator = Orchestrator()


@router.get("/overview", response_model=ApiResponse)
async def overview(student_id: str = Query(..., min_length=1)) -> ApiResponse:
    request_id = new_id()
    try:
        return ApiResponse(request_id=request_id, success=True, data=evaluation_overview(student_id))
    except Exception as e:
        return ApiResponse(
            request_id=request_id,
            success=False,
            error={"code": "EVALUATION_OVERVIEW_ERROR", "message": str(e)},
        )


@router.post("/report", response_model=ApiResponse)
async def report(req: EvaluateReportRequest) -> ApiResponse:
    request_id = new_id()
    try:
        result = await orchestrator.evaluate(student_id=req.student_id)
        return ApiResponse(request_id=request_id, success=True, data=result)
    except Exception as e:
        return ApiResponse(request_id=request_id, success=False, error={"code": "EVALUATE_ERROR", "message": str(e)})


@router.post("/report/stream")
async def report_stream(req: EvaluateReportRequest):
    request_id = new_id()

    async def work(on_chunk):
        return await orchestrator.evaluate(student_id=req.student_id, on_chunk=on_chunk)

    def text(result: dict) -> str:
        report = result.get("report", result)
        parts = [str(report.get("summary", "") or report.get("conclusion", ""))]
        for key in ("findings", "weak_points", "suggestions", "recommendations", "next_actions"):
            value = report.get(key)
            if isinstance(value, list):
                parts.extend(str(x) for x in value)
            elif value:
                parts.append(str(value))
        return "\n".join([p for p in parts if p])

    return stream_response(
        stream_live_operation(
            request_id=request_id,
            work=work,
            start_message="开始生成学习效果评估报告",
            final_key="result",
            fallback_text=text,
            chunk_path="report_text",
        )
    )

