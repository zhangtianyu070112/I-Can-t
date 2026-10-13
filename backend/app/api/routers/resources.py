from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.core.ids import new_id
from app.repo import get_resource_item, list_resources
from app.schemas import ApiResponse
from app.services.resource_structure import extract_resource_structures


router = APIRouter(prefix="/api/resources", tags=["resources"])


@router.get("/{resource_id}", response_model=ApiResponse)
async def get_resource(resource_id: str, inline: bool = Query(default=False)) -> ApiResponse:
    request_id = new_id()
    item = get_resource_item(resource_id)
    if not item:
        raise HTTPException(status_code=404, detail="resource_not_found")
    if inline:
        p = settings.data_path / Path(item["content_uri"])
        if p.exists():
            content = p.read_text(encoding="utf-8")
            item["content"] = content
            item.update(extract_resource_structures(str(item.get("type", "")), content))
    item["download_url"] = f"/{item['content_uri']}"
    return ApiResponse(request_id=request_id, success=True, data=item)


@router.get("", response_model=ApiResponse)
async def list_student_resources(student_id: str = Query(..., min_length=1)) -> ApiResponse:
    request_id = new_id()
    return ApiResponse(request_id=request_id, success=True, data={"resources": list_resources(student_id)})

