from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel


PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "backend" / ".env", override=True)


class Settings(BaseModel):
    app_env: str = "dev"
    app_host: str = "127.0.0.1"
    app_port: int = 8000

    data_dir: str = "./data"

    llm_provider: str = "openai_compatible"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_sec: int = 60
    glm_timeout_sec: int = 180
    llm_chat_path: str = "/v1/chat/completions"
    llm_auth_header: str = "Authorization"
    llm_auth_prefix: str = "Bearer "

    llm_profile_base_url: str = ""
    llm_profile_api_key: str = ""
    llm_profile_model: str = ""
    llm_profile_chat_path: str = ""
    llm_profile_auth_header: str = ""
    llm_profile_auth_prefix: str = ""

    llm_clarify_base_url: str = ""
    llm_clarify_api_key: str = ""
    llm_clarify_model: str = ""
    llm_clarify_chat_path: str = ""
    llm_clarify_auth_header: str = ""
    llm_clarify_auth_prefix: str = ""

    llm_generate_base_url: str = ""
    llm_generate_api_key: str = ""
    llm_generate_model: str = ""
    llm_generate_chat_path: str = ""
    llm_generate_auth_header: str = ""
    llm_generate_auth_prefix: str = ""

    llm_plan_base_url: str = ""
    llm_plan_api_key: str = ""
    llm_plan_model: str = ""
    llm_plan_chat_path: str = ""
    llm_plan_auth_header: str = ""
    llm_plan_auth_prefix: str = ""

    llm_tutor_base_url: str = ""
    llm_tutor_api_key: str = ""
    llm_tutor_model: str = ""
    llm_tutor_chat_path: str = ""
    llm_tutor_auth_header: str = ""
    llm_tutor_auth_prefix: str = ""

    llm_evaluate_base_url: str = ""
    llm_evaluate_api_key: str = ""
    llm_evaluate_model: str = ""
    llm_evaluate_chat_path: str = ""
    llm_evaluate_auth_header: str = ""
    llm_evaluate_auth_prefix: str = ""

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir).resolve()

    @property
    def db_path(self) -> Path:
        return self.data_path / "app.db"

    @property
    def files_path(self) -> Path:
        return self.data_path / "files"


settings = Settings(
    app_env=(__import__("os").environ.get("APP_ENV") or "dev"),
    app_host=(__import__("os").environ.get("APP_HOST") or "127.0.0.1"),
    app_port=int(__import__("os").environ.get("APP_PORT") or "8000"),
    data_dir=(__import__("os").environ.get("DATA_DIR") or "./data"),
    llm_provider=(__import__("os").environ.get("LLM_PROVIDER") or "openai_compatible"),
    llm_base_url=(__import__("os").environ.get("LLM_BASE_URL") or ""),
    llm_api_key=(__import__("os").environ.get("LLM_API_KEY") or ""),
    llm_model=(__import__("os").environ.get("LLM_MODEL") or ""),
    llm_timeout_sec=int(__import__("os").environ.get("LLM_TIMEOUT_SEC") or "60"),
    glm_timeout_sec=int(__import__("os").environ.get("GLM_TIMEOUT_SEC") or "180"),
    llm_chat_path=(__import__("os").environ.get("LLM_CHAT_PATH") or "/v1/chat/completions"),
    llm_auth_header=(__import__("os").environ.get("LLM_AUTH_HEADER") or "Authorization"),
    llm_auth_prefix=(__import__("os").environ.get("LLM_AUTH_PREFIX") or "Bearer "),

    llm_profile_base_url=(__import__("os").environ.get("LLM_PROFILE_BASE_URL") or ""),
    llm_profile_api_key=(__import__("os").environ.get("LLM_PROFILE_API_KEY") or ""),
    llm_profile_model=(__import__("os").environ.get("LLM_PROFILE_MODEL") or ""),
    llm_profile_chat_path=(__import__("os").environ.get("LLM_PROFILE_CHAT_PATH") or ""),
    llm_profile_auth_header=(__import__("os").environ.get("LLM_PROFILE_AUTH_HEADER") or ""),
    llm_profile_auth_prefix=(__import__("os").environ.get("LLM_PROFILE_AUTH_PREFIX") or ""),

    llm_clarify_base_url=(__import__("os").environ.get("LLM_CLARIFY_BASE_URL") or ""),
    llm_clarify_api_key=(__import__("os").environ.get("LLM_CLARIFY_API_KEY") or ""),
    llm_clarify_model=(__import__("os").environ.get("LLM_CLARIFY_MODEL") or ""),
    llm_clarify_chat_path=(__import__("os").environ.get("LLM_CLARIFY_CHAT_PATH") or ""),
    llm_clarify_auth_header=(__import__("os").environ.get("LLM_CLARIFY_AUTH_HEADER") or ""),
    llm_clarify_auth_prefix=(__import__("os").environ.get("LLM_CLARIFY_AUTH_PREFIX") or ""),

    llm_generate_base_url=(__import__("os").environ.get("LLM_GENERATE_BASE_URL") or ""),
    llm_generate_api_key=(__import__("os").environ.get("LLM_GENERATE_API_KEY") or ""),
    llm_generate_model=(__import__("os").environ.get("LLM_GENERATE_MODEL") or ""),
    llm_generate_chat_path=(__import__("os").environ.get("LLM_GENERATE_CHAT_PATH") or ""),
    llm_generate_auth_header=(__import__("os").environ.get("LLM_GENERATE_AUTH_HEADER") or ""),
    llm_generate_auth_prefix=(__import__("os").environ.get("LLM_GENERATE_AUTH_PREFIX") or ""),

    llm_plan_base_url=(__import__("os").environ.get("LLM_PLAN_BASE_URL") or ""),
    llm_plan_api_key=(__import__("os").environ.get("LLM_PLAN_API_KEY") or ""),
    llm_plan_model=(__import__("os").environ.get("LLM_PLAN_MODEL") or ""),
    llm_plan_chat_path=(__import__("os").environ.get("LLM_PLAN_CHAT_PATH") or ""),
    llm_plan_auth_header=(__import__("os").environ.get("LLM_PLAN_AUTH_HEADER") or ""),
    llm_plan_auth_prefix=(__import__("os").environ.get("LLM_PLAN_AUTH_PREFIX") or ""),

    llm_tutor_base_url=(__import__("os").environ.get("LLM_TUTOR_BASE_URL") or ""),
    llm_tutor_api_key=(__import__("os").environ.get("LLM_TUTOR_API_KEY") or ""),
    llm_tutor_model=(__import__("os").environ.get("LLM_TUTOR_MODEL") or ""),
    llm_tutor_chat_path=(__import__("os").environ.get("LLM_TUTOR_CHAT_PATH") or ""),
    llm_tutor_auth_header=(__import__("os").environ.get("LLM_TUTOR_AUTH_HEADER") or ""),
    llm_tutor_auth_prefix=(__import__("os").environ.get("LLM_TUTOR_AUTH_PREFIX") or ""),

    llm_evaluate_base_url=(__import__("os").environ.get("LLM_EVALUATE_BASE_URL") or ""),
    llm_evaluate_api_key=(__import__("os").environ.get("LLM_EVALUATE_API_KEY") or ""),
    llm_evaluate_model=(__import__("os").environ.get("LLM_EVALUATE_MODEL") or ""),
    llm_evaluate_chat_path=(__import__("os").environ.get("LLM_EVALUATE_CHAT_PATH") or ""),
    llm_evaluate_auth_header=(__import__("os").environ.get("LLM_EVALUATE_AUTH_HEADER") or ""),
    llm_evaluate_auth_prefix=(__import__("os").environ.get("LLM_EVALUATE_AUTH_PREFIX") or ""),
)
