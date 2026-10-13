from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, Query, Request

from app.core.ids import new_id
from app.evolution import EvolutionEngine
from app.schemas import ApiResponse
from app.services.knowledge_hub import (
    graph_data,
    ingest_textbook,
    mastery_data,
    overview,
    record_search_event,
    search_index,
    track_node,
)
from app.services.learning_state import knowledge_workspace


router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
evolution_engine = EvolutionEngine()


class TrackNodeRequest(BaseModel):
    student_id: str
    node_id: str
    score: float = 80
    note: str = ""


@router.post("/textbook", response_model=ApiResponse)
async def upload_textbook(
    request: Request,
    student_id: str = Query(..., min_length=1),
    filename: str = Query(..., min_length=1),
) -> ApiResponse:
    request_id = new_id()
    try:
        content = await request.body()
        data = ingest_textbook(student_id=student_id, filename=filename, content=content)
        return ApiResponse(request_id=request_id, success=True, data=data)
    except Exception as exc:
        return ApiResponse(request_id=request_id, success=False, error={"code": "TEXTBOOK_UPLOAD_ERROR", "message": str(exc)})


@router.get("/workspace", response_model=ApiResponse)
async def workspace(student_id: str = Query(..., min_length=1)) -> ApiResponse:
    request_id = new_id()
    try:
        return ApiResponse(request_id=request_id, success=True, data=knowledge_workspace(student_id))
    except Exception as e:
        return ApiResponse(
            request_id=request_id,
            success=False,
            error={"code": "KNOWLEDGE_WORKSPACE_ERROR", "message": str(e)},
        )


@router.get("/overview", response_model=ApiResponse)
async def get_overview(student_id: str = Query(..., min_length=1)) -> ApiResponse:
    request_id = new_id()
    try:
        return ApiResponse(request_id=request_id, success=True, data=overview(student_id))
    except Exception as e:
        return ApiResponse(request_id=request_id, success=False, error={"code": "KNOWLEDGE_OVERVIEW_ERROR", "message": str(e)})


@router.get("/search", response_model=ApiResponse)
async def search(
    student_id: str = Query(..., min_length=1),
    q: str = Query(default="", min_length=0),
    limit: int = Query(default=5, ge=1, le=10),
) -> ApiResponse:
    request_id = new_id()
    try:
        results = search_index(student_id=student_id, query=q, limit=limit)
        if q.strip():
            record_search_event(student_id=student_id, query=q, count=len(results))
        return ApiResponse(request_id=request_id, success=True, data={"query": q, "results": results})
    except Exception as e:
        return ApiResponse(request_id=request_id, success=False, error={"code": "KNOWLEDGE_SEARCH_ERROR", "message": str(e)})


@router.get("/graph", response_model=ApiResponse)
async def get_graph(
    student_id: str = Query(..., min_length=1),
    course: str = "",
    source_type: str = Query(default="all", pattern="^(all|course|generated)$"),
    keyword: str = "",
    max_nodes: int = Query(default=56, ge=12, le=100),
) -> ApiResponse:
    request_id = new_id()
    try:
        return ApiResponse(
            request_id=request_id,
            success=True,
            data=graph_data(student_id, course, source_type, keyword, max_nodes),
        )
    except Exception as e:
        return ApiResponse(request_id=request_id, success=False, error={"code": "KNOWLEDGE_GRAPH_ERROR", "message": str(e)})


@router.get("/mastery", response_model=ApiResponse)
async def get_mastery(student_id: str = Query(..., min_length=1)) -> ApiResponse:
    request_id = new_id()
    try:
        return ApiResponse(request_id=request_id, success=True, data=mastery_data(student_id))
    except Exception as e:
        return ApiResponse(request_id=request_id, success=False, error={"code": "MASTERY_ERROR", "message": str(e)})


@router.post("/track", response_model=ApiResponse)
async def track(req: TrackNodeRequest) -> ApiResponse:
    request_id = new_id()
    try:
        result = track_node(student_id=req.student_id, node_id=req.node_id, score=req.score, note=req.note)
        evolution_result = None
        if req.score < 60:
            evolution_result = await evolution_engine.evaluate_and_evolve(
                student_id=req.student_id,
                trigger_event="mastery_low_score",
                context_data={
                    "node_id": req.node_id,
                    "score": req.score,
                    "note": req.note,
                },
            )
        return ApiResponse(request_id=request_id, success=True, data={**result, "evolution": evolution_result})
    except Exception as e:
        return ApiResponse(request_id=request_id, success=False, error={"code": "MASTERY_TRACK_ERROR", "message": str(e)})
