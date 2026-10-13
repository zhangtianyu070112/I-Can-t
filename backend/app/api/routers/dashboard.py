from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.ids import new_id
from app.schemas import ApiResponse
from app.services.learning_state import activity_feed, learning_overview


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=ApiResponse)
async def overview(student_id: str = Query(..., min_length=1)) -> ApiResponse:
    request_id = new_id()
    try:
        return ApiResponse(request_id=request_id, success=True, data=learning_overview(student_id))
    except Exception as exc:
        return ApiResponse(
            request_id=request_id,
            success=False,
            error={"code": "DASHBOARD_OVERVIEW_ERROR", "message": str(exc)},
        )


@router.get("/activity", response_model=ApiResponse)
async def activity(
    student_id: str = Query(..., min_length=1),
    limit: int = Query(default=12, ge=1, le=50),
) -> ApiResponse:
    request_id = new_id()
    try:
        return ApiResponse(
            request_id=request_id,
            success=True,
            data={"items": activity_feed(student_id, limit=limit)},
        )
    except Exception as exc:
        return ApiResponse(
            request_id=request_id,
            success=False,
            error={"code": "DASHBOARD_ACTIVITY_ERROR", "message": str(exc)},
        )
