from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.llm import get_llm_client_for, is_llm_configured


router = APIRouter(prefix="/api/mindmap", tags=["mindmap"])


class MindMapGenerateRequest(BaseModel):
    topic: str = ""
    requirements: str = ""
    style: str = "清晰教学风格"


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _glm_api_key() -> str:
    return (
        _env("GLM_TEXT_API_KEY")
        or _env("GLM_API_KEY")
        or _env("ZHIPU_API_KEY")
        or _env("BIGMODEL_API_KEY")
        or _env("GLM_IMAGE_API_KEY")
    )


def _glm_chat_url() -> str:
    base_url = (_env("GLM_TEXT_BASE_URL") or _env("GLM_BASE_URL") or "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
    endpoint = _env("GLM_TEXT_ENDPOINT", "/chat/completions")
    if not endpoint.startswith("/"):
        endpoint = f"/{endpoint}"
    return f"{base_url}{endpoint}"


def _extract_mermaid(text: str) -> str:
    match = re.search(r"```mermaid\s*\n([\s\S]*?)```", text or "", re.I)
    if match:
        return match.group(1).strip()
    match = re.search(r"```mermaid\s+(mindmap[\s\S]*?)```", text or "", re.I)
    if match:
        return match.group(1).strip()
    match = re.search(r"```\s*\n(mindmap[\s\S]*?)```", text or "", re.I)
    if match:
        return match.group(1).strip()
    start = re.search(r"(^|\n)\s*mindmap\s*\n", text or "", re.I)
    if not start:
        return ""
    return (text or "")[start.start():].strip()


@router.get("/health")
async def mindmap_health() -> dict[str, Any]:
    return {
        "success": True,
        "router": "mindmap",
        "zhipu_configured": bool(_glm_api_key()),
        "model": _env("GLM_TEXT_MODEL", "glm-4-flash"),
    }


def parse_mermaid_to_tree(mermaid_text: str) -> dict[str, Any] | None:
    lines = (mermaid_text or "").replace("\t", "  ").splitlines()
    parsed: list[tuple[int, str]] = []
    for raw in lines:
        if not raw.strip() or raw.strip().lower() == "mindmap":
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        text = raw.strip()
        text = re.sub(r"^root\s*\(\((.*?)\)\)$", r"\1", text)
        text = re.sub(r"^\(\((.*?)\)\)$", r"\1", text)
        text = re.sub(r"^\[(.*?)\]$", r"\1", text)
        text = re.sub(r"^\((.*?)\)$", r"\1", text)
        if text:
            parsed.append((max(0, indent // 2), text))
    if not parsed:
        return None

    root: dict[str, Any] | None = None
    stack: list[tuple[int, dict[str, Any]]] = []
    for level, text in parsed:
        node = {"name": text, "content": text, "children": []}
        while stack and stack[-1][0] >= level:
            stack.pop()
        if stack:
            stack[-1][1]["children"].append(node)
        else:
            root = node if root is None else root
            if root is not node:
                root["children"].append(node)
        stack.append((level, node))
    return root


def _fallback_tree(topic: str) -> dict[str, Any]:
    return {
        "name": topic,
        "content": topic,
        "children": [
            {"name": "核心概念", "content": "核心概念", "children": []},
            {"name": "知识结构", "content": "知识结构", "children": []},
            {"name": "学习重点", "content": "学习重点", "children": []},
            {"name": "应用场景", "content": "应用场景", "children": []},
        ],
    }


async def _generate_with_zhipu(req: MindMapGenerateRequest) -> str:
    api_key = _glm_api_key()
    topic = (req.topic or req.requirements or "").strip()
    model = _env("GLM_TEXT_MODEL", "glm-4-flash")
    prompt = f"""请为主题“{topic}”生成高质量中文学习思维导图。
用户补充要求：{req.requirements or topic}
风格：{req.style}

必须满足：
1. 只使用智谱模型生成内容。
2. 必须输出一个 Mermaid mindmap 代码块。
3. 中心主题下面至少 5 个一级分支，每个一级分支至少 3 个二级节点。
4. 层级清楚，适合教学复习，不要空泛。
5. Mermaid 缩进每层 2 个空格，不要在节点中使用会破坏 Mermaid 的特殊符号。
6. 代码块后可以附 3-5 条简短学习建议。

格式示例：
```mermaid
mindmap
  root((主题))
    一级分支
      二级节点
```
"""
    if not api_key:
        if not is_llm_configured("generate"):
            raise RuntimeError("思维导图模型尚未配置")
        llm = get_llm_client_for("generate")
        return await llm.chat_text(
            system="你是知识结构设计专家，必须输出可解析的 Mermaid mindmap 代码块。",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.45,
            max_tokens=1800,
        )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是知识结构设计专家，擅长输出 Mermaid mindmap。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.45,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=float(_env("GLM_TEXT_TIMEOUT", "90") or 90)) as client:
        resp = await client.post(_glm_chat_url(), json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"]


@router.post("/generate")
async def mindmap_generate(req: MindMapGenerateRequest) -> dict[str, Any]:
    topic = (req.topic or req.requirements or "").strip()
    if not topic:
        return {"success": False, "error": "请输入思维导图主题"}

    try:
        content = await _generate_with_zhipu(req)
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] if exc.response is not None else ""
        return {"success": False, "error": f"智谱思维导图生成失败：HTTP {exc.response.status_code if exc.response else 'unknown'} {detail}"}
    except Exception as exc:
        return {"success": False, "error": f"智谱思维导图生成失败：{exc}"}

    mermaid = _extract_mermaid(content)
    tree = parse_mermaid_to_tree(mermaid)
    if not tree:
        return {
            "success": False,
            "error": "模型返回内容无法解析为 Mermaid mindmap，未生成任何模板兜底数据，请调整要求后重试",
        }
    return {
        "success": True,
        "type": "mindmap",
        "title": topic,
        "content": content,
        "mermaid_source": mermaid,
        "tree_data": tree,
        "model": _env("GLM_TEXT_MODEL", "glm-4-flash") if _glm_api_key() else "项目通用生成模型",
    }
