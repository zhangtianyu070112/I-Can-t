from __future__ import annotations

import os
from dataclasses import dataclass

from app.core.config import settings
from app.llm.openai_compatible import OpenAICompatibleClient


@dataclass(frozen=True)
class LLMRoute:
    base_url: str
    api_key: str
    model: str
    chat_path: str
    auth_header: str
    auth_prefix: str

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model and self.chat_path)


def _fallback(v: str, default: str) -> str:
    return v if v else default


def resolve_route(use_case: str) -> LLMRoute:
    use_case = use_case.lower().strip()
    if use_case == "profile":
        return LLMRoute(
            base_url=_fallback(settings.llm_profile_base_url, settings.llm_base_url),
            api_key=_fallback(settings.llm_profile_api_key, settings.llm_api_key),
            model=_fallback(settings.llm_profile_model, settings.llm_model),
            chat_path=_fallback(settings.llm_profile_chat_path, settings.llm_chat_path),
            auth_header=_fallback(settings.llm_profile_auth_header, settings.llm_auth_header),
            auth_prefix=_fallback(settings.llm_profile_auth_prefix, settings.llm_auth_prefix),
        )
    if use_case == "clarify":
        return LLMRoute(
            base_url=_fallback(settings.llm_clarify_base_url, settings.llm_base_url),
            api_key=_fallback(settings.llm_clarify_api_key, settings.llm_api_key),
            model=_fallback(settings.llm_clarify_model, settings.llm_model),
            chat_path=_fallback(settings.llm_clarify_chat_path, settings.llm_chat_path),
            auth_header=_fallback(settings.llm_clarify_auth_header, settings.llm_auth_header),
            auth_prefix=_fallback(settings.llm_clarify_auth_prefix, settings.llm_auth_prefix),
        )
    if use_case == "generate":
        return LLMRoute(
            base_url=_fallback(settings.llm_generate_base_url, settings.llm_base_url),
            api_key=_fallback(settings.llm_generate_api_key, settings.llm_api_key),
            model=_fallback(settings.llm_generate_model, settings.llm_model),
            chat_path=_fallback(settings.llm_generate_chat_path, settings.llm_chat_path),
            auth_header=_fallback(settings.llm_generate_auth_header, settings.llm_auth_header),
            auth_prefix=_fallback(settings.llm_generate_auth_prefix, settings.llm_auth_prefix),
        )
    if use_case == "plan":
        return LLMRoute(
            base_url=_fallback(settings.llm_plan_base_url, settings.llm_base_url),
            api_key=_fallback(settings.llm_plan_api_key, settings.llm_api_key),
            model=_fallback(settings.llm_plan_model, settings.llm_model),
            chat_path=_fallback(settings.llm_plan_chat_path, settings.llm_chat_path),
            auth_header=_fallback(settings.llm_plan_auth_header, settings.llm_auth_header),
            auth_prefix=_fallback(settings.llm_plan_auth_prefix, settings.llm_auth_prefix),
        )
    if use_case == "tutor":
        return LLMRoute(
            base_url=_fallback(settings.llm_tutor_base_url, settings.llm_base_url),
            api_key=_fallback(settings.llm_tutor_api_key, settings.llm_api_key),
            model=_fallback(settings.llm_tutor_model, settings.llm_model),
            chat_path=_fallback(settings.llm_tutor_chat_path, settings.llm_chat_path),
            auth_header=_fallback(settings.llm_tutor_auth_header, settings.llm_auth_header),
            auth_prefix=_fallback(settings.llm_tutor_auth_prefix, settings.llm_auth_prefix),
        )
    if use_case == "evaluate":
        return LLMRoute(
            base_url=_fallback(settings.llm_evaluate_base_url, settings.llm_base_url),
            api_key=_fallback(settings.llm_evaluate_api_key, settings.llm_api_key),
            model=_fallback(settings.llm_evaluate_model, settings.llm_model),
            chat_path=_fallback(settings.llm_evaluate_chat_path, settings.llm_chat_path),
            auth_header=_fallback(settings.llm_evaluate_auth_header, settings.llm_auth_header),
            auth_prefix=_fallback(settings.llm_evaluate_auth_prefix, settings.llm_auth_prefix),
        )
    return LLMRoute(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        chat_path=settings.llm_chat_path,
        auth_header=settings.llm_auth_header,
        auth_prefix=settings.llm_auth_prefix,
    )


def is_llm_configured(use_case: str) -> bool:
    return resolve_route(use_case).configured


def get_llm_client_for(use_case: str) -> OpenAICompatibleClient:
    route = resolve_route(use_case)
    return OpenAICompatibleClient(
        base_url=route.base_url,
        api_key=route.api_key,
        model=route.model,
        timeout_sec=settings.llm_timeout_sec,
        chat_path=route.chat_path,
        auth_header=route.auth_header,
        auth_prefix=route.auth_prefix,
    )


def resolve_glm_route() -> LLMRoute:
    base_url = (
        os.environ.get("GLM_TEXT_BASE_URL")
        or os.environ.get("GLM_BASE_URL")
        or "https://open.bigmodel.cn/api/paas/v4"
    ).rstrip("/")
    chat_path = os.environ.get("GLM_TEXT_ENDPOINT") or "/chat/completions"
    if not chat_path.startswith("/"):
        chat_path = f"/{chat_path}"
    return LLMRoute(
        base_url=base_url,
        api_key=(
            os.environ.get("GLM_TEXT_API_KEY")
            or os.environ.get("GLM_API_KEY")
            or os.environ.get("ZHIPU_API_KEY")
            or os.environ.get("BIGMODEL_API_KEY")
            or ""
        ).strip(),
        model=(os.environ.get("GLM_TEXT_MODEL") or "glm-4-flash").strip(),
        chat_path=chat_path,
        auth_header="Authorization",
        auth_prefix="Bearer ",
    )


def is_glm_configured() -> bool:
    return resolve_glm_route().configured


def get_glm_client() -> OpenAICompatibleClient:
    route = resolve_glm_route()
    return OpenAICompatibleClient(
        base_url=route.base_url,
        api_key=route.api_key,
        model=route.model,
        timeout_sec=settings.glm_timeout_sec,
        chat_path=route.chat_path,
        auth_header=route.auth_header,
        auth_prefix=route.auth_prefix,
    )
