from __future__ import annotations

import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.ids import new_id
from app.repo import get_resource_item, insert_learning_event
from app.schemas import ApiResponse, ExportPackageRequest


router = APIRouter(prefix="/api/export", tags=["export"])


class ExportImageRequest(BaseModel):
    image_url: str = Field(min_length=1)
    title: str = "生成图片"
    file_name: str = "生成图片.png"
    headers: dict[str, str] = Field(default_factory=dict)


def _resolve_local_image(image_url: str) -> Path:
    parsed = urlsplit(image_url.strip())
    url_path = unquote(parsed.path or "")
    if not url_path.startswith("/files/"):
        raise HTTPException(status_code=400, detail="仅支持导出本系统已经保存的图片")

    files_root = settings.files_path.resolve()
    candidate = (files_root / url_path.removeprefix("/files/")).resolve()
    try:
        candidate.relative_to(files_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="图片地址不合法") from exc

    if candidate.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
        raise HTTPException(status_code=400, detail="目标文件不是可导出的图片")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="图片文件不存在或已被清理")
    return candidate


@router.post("/image")
async def export_image(req: ExportImageRequest) -> FileResponse:
    image_path = _resolve_local_image(req.image_url)
    requested_name = Path(req.file_name or "").name.strip()
    download_name = requested_name or f"{(req.title or '生成图片').strip()}{image_path.suffix.lower()}"
    if Path(download_name).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
        download_name = f"{Path(download_name).stem or '生成图片'}{image_path.suffix.lower()}"
    return FileResponse(image_path, filename=download_name, media_type=f"image/{image_path.suffix.lower().lstrip('.').replace('jpg', 'jpeg')}")


@router.post("/package", response_model=ApiResponse)
async def export_package(req: ExportPackageRequest) -> ApiResponse:
    request_id = new_id()
    export_dir = settings.data_path / "exports" / req.student_id
    export_dir.mkdir(parents=True, exist_ok=True)
    zip_name = f"{new_id()}.zip"
    zip_path = export_dir / zip_name

    resource_ids = req.resource_ids
    if not resource_ids:
        return ApiResponse(
            request_id=request_id,
            success=False,
            error={"code": "EXPORT_EMPTY", "message": "resource_ids 为空"},
        )

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rid in resource_ids:
            item = get_resource_item(rid)
            if not item:
                continue
            file_path = settings.data_path / Path(item["content_uri"])
            if file_path.exists():
                arcname = f"{item['type']}-{item['title']}-{rid}{file_path.suffix}"
                zf.write(file_path, arcname=arcname)

    insert_learning_event(req.student_id, "export", {"zip": str(zip_path)})
    return ApiResponse(
        request_id=request_id,
        success=True,
        data={"download_url": f"/exports/{req.student_id}/{zip_name}", "file_name": zip_name},
    )

