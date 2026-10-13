from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.ids import new_id
from app.llm.openai_compatible import OpenAICompatibleClient
from app.schemas import ApiResponse


router = APIRouter(prefix="/api/config", tags=["config"])


class LLMConfigRequest(BaseModel):
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    chat_path: str = "/v1/chat/completions"
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer "
    timeout_sec: int = Field(default=60, ge=5, le=300)
    apply_to_all_routes: bool = True


class LLMTestRequest(LLMConfigRequest):
    prompt: str = "请用一句中文回复：API 连接成功。"


@router.get("/llm", response_model=ApiResponse)
async def get_llm_config() -> ApiResponse:
    request_id = new_id()
    data = {
        "base_url": settings.llm_base_url,
        "api_key_masked": _mask_key(settings.llm_api_key),
        "configured": bool(settings.llm_base_url and settings.llm_api_key and settings.llm_model),
        "model": settings.llm_model,
        "chat_path": settings.llm_chat_path,
        "auth_header": settings.llm_auth_header,
        "auth_prefix": settings.llm_auth_prefix,
        "timeout_sec": settings.llm_timeout_sec,
    }
    return ApiResponse(request_id=request_id, success=True, data=data)


@router.post("/llm", response_model=ApiResponse)
async def save_llm_config(req: LLMConfigRequest) -> ApiResponse:
    request_id = new_id()
    try:
        _apply_runtime_settings(req)
        _write_env(req)
        return ApiResponse(
            request_id=request_id,
            success=True,
            data={
                "configured": bool(settings.llm_base_url and settings.llm_api_key and settings.llm_model),
                "api_key_masked": _mask_key(settings.llm_api_key),
                "message": "LLM 配置已保存到本地 .env，并已在当前后端进程生效。",
            },
        )
    except Exception as e:
        return ApiResponse(request_id=request_id, success=False, error={"code": "CONFIG_SAVE_ERROR", "message": str(e)})


@router.post("/llm/test", response_model=ApiResponse)
async def test_llm_config(req: LLMTestRequest) -> ApiResponse:
    request_id = new_id()
    route = req if req.base_url and req.api_key and req.model else _request_from_settings()
    try:
        client = OpenAICompatibleClient(
            base_url=route.base_url,
            api_key=route.api_key,
            model=route.model,
            timeout_sec=route.timeout_sec,
            chat_path=route.chat_path,
            auth_header=route.auth_header,
            auth_prefix=route.auth_prefix,
        )
        text = await client.chat_text(
            system="你是 API 连通性测试助手。请简短回答。",
            messages=[{"role": "user", "content": req.prompt}],
            temperature=0.1,
        )
        return ApiResponse(request_id=request_id, success=True, data={"ok": True, "reply": text})
    except Exception as e:
        message = str(e) or e.__class__.__name__
        return ApiResponse(request_id=request_id, success=False, error={"code": "LLM_TEST_ERROR", "message": message})


def _request_from_settings() -> LLMConfigRequest:
    return LLMConfigRequest(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        chat_path=settings.llm_chat_path,
        auth_header=settings.llm_auth_header,
        auth_prefix=settings.llm_auth_prefix,
        timeout_sec=settings.llm_timeout_sec,
    )


def _apply_runtime_settings(req: LLMConfigRequest) -> None:
    settings.llm_base_url = req.base_url.strip().rstrip("/")
    settings.llm_api_key = req.api_key.strip()
    settings.llm_model = req.model.strip()
    settings.llm_chat_path = req.chat_path.strip() or "/v1/chat/completions"
    settings.llm_auth_header = req.auth_header.strip() or "Authorization"
    settings.llm_auth_prefix = req.auth_prefix if req.auth_prefix is not None else "Bearer "
    settings.llm_timeout_sec = req.timeout_sec

    if req.apply_to_all_routes:
        for use_case in ("profile", "clarify", "generate", "plan", "tutor", "evaluate"):
            setattr(settings, f"llm_{use_case}_base_url", "")
            setattr(settings, f"llm_{use_case}_api_key", "")
            setattr(settings, f"llm_{use_case}_model", "")
            setattr(settings, f"llm_{use_case}_chat_path", "")
            setattr(settings, f"llm_{use_case}_auth_header", "")
            setattr(settings, f"llm_{use_case}_auth_prefix", "")


def _write_env(req: LLMConfigRequest) -> None:
    env_path = _project_root() / ".env"
    existing = _read_env(env_path)
    updates = {
        "LLM_PROVIDER": "openai_compatible",
        "LLM_BASE_URL": req.base_url.strip().rstrip("/"),
        "LLM_API_KEY": req.api_key.strip(),
        "LLM_MODEL": req.model.strip(),
        "LLM_CHAT_PATH": req.chat_path.strip() or "/v1/chat/completions",
        "LLM_AUTH_HEADER": req.auth_header.strip() or "Authorization",
        "LLM_AUTH_PREFIX": req.auth_prefix if req.auth_prefix is not None else "Bearer ",
        "LLM_TIMEOUT_SEC": str(req.timeout_sec),
    }
    if req.apply_to_all_routes:
        for use_case in ("PROFILE", "CLARIFY", "GENERATE", "PLAN", "TUTOR", "EVALUATE"):
            updates[f"LLM_{use_case}_BASE_URL"] = ""
            updates[f"LLM_{use_case}_API_KEY"] = ""
            updates[f"LLM_{use_case}_MODEL"] = ""
            updates[f"LLM_{use_case}_CHAT_PATH"] = ""
            updates[f"LLM_{use_case}_AUTH_HEADER"] = ""
            updates[f"LLM_{use_case}_AUTH_PREFIX"] = ""

    existing.update(updates)
    lines = [f"{key}={_quote_env(value)}" for key, value in existing.items()]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def _quote_env(value: str) -> str:
    if value == "":
        return ""
    if any(ch.isspace() for ch in value) or "#" in value:
        return '"' + value.replace('"', '\\"') + '"'
    return value


def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}...{key[-4:]}"
