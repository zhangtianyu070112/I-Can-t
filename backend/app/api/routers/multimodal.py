from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.streaming import stream_live_operation, stream_response
from app.core.config import settings
from app.core.ids import new_id
from app.llm import get_llm_client_for, is_llm_configured
from app.repo import insert_learning_event, insert_resource_item
from app.schemas import ApiResponse


router = APIRouter(prefix="/api/multimodal", tags=["multimodal"])


class TopicRequest(BaseModel):
    student_id: str = Field(min_length=1)
    topic: str
    save: bool = True


class CodeCaseRequest(TopicRequest):
    language: str = "Python"


class VoiceLessonRequest(TopicRequest):
    mode: str = Field(default="general", description="general/english/interview/coding")


class WritingRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=12000)


@router.post("/writing", response_model=ApiResponse)
async def writing(req: WritingRequest) -> ApiResponse:
    request_id = new_id()
    if not is_llm_configured("generate"):
        return ApiResponse(request_id=request_id, success=False, error={"code": "WRITING_MODEL_NOT_CONFIGURED", "message": "AI 写作模型尚未配置"})
    try:
        llm = get_llm_client_for("generate")
        content = await llm.chat_text(
            system=(
                "你是独立的中文内容与知识讲解助手。只依据本次用户输入回答，不读取学习画像、知识库、历史对话或其他功能数据。"
                "知识类请求应紧扣用户指定的对象、语言和主题直接讲解，不得擅自改成编程案例，也不得替换为其他编程语言。"
                "写作类请求直接输出可交付正文；使用自然段和必要的小标题，不使用 Markdown 标记、代码围栏、星号或井号。"
            ),
            messages=[{"role": "user", "content": req.prompt.strip()}],
            temperature=0.72,
            max_tokens=2600,
        )
        return ApiResponse(request_id=request_id, success=True, data={"content": content.strip()})
    except Exception as exc:
        return ApiResponse(request_id=request_id, success=False, error={"code": "WRITING_GENERATE_ERROR", "message": f"AI 写作生成失败：{exc}"})


@router.get("/capabilities", response_model=ApiResponse)
async def capabilities() -> ApiResponse:
    return ApiResponse(
        request_id=new_id(),
        success=True,
        data={
            "source": "桌面/队友成果",
            "integrated_as": "FastAPI + Vue 多模态实验室",
            "items": [
                {
                    "key": "video",
                    "name": "教学视频推荐",
                    "from_teammate": "VideoGenerator / /api/video/generate",
                    "current_route": "/api/multimodal/video-search",
                    "value": "生成国内平台检索词和直达搜索入口，可保存为资源。",
                },
                {
                    "key": "code",
                    "name": "代码实操案例",
                    "from_teammate": "CodeGenerator / CodeAgent",
                    "current_route": "/api/multimodal/code-case",
                    "value": "按主题生成可运行练习、步骤、验收标准和扩展任务。",
                },
                {
                    "key": "voice",
                    "name": "语音/视频辅导方案",
                    "from_teammate": "VoiceAgent / RealtimeVideoCall",
                    "current_route": "/api/multimodal/voice-lesson",
                    "value": "保留实时语音教学设计思路，输出可演示的语音辅导脚本和配置清单。",
                },
            ],
        },
    )


@router.post("/video-search", response_model=ApiResponse)
async def video_search(req: TopicRequest) -> ApiResponse:
    request_id = new_id()
    topic = req.topic.strip()
    if not topic:
        return ApiResponse(request_id=request_id, success=False, error={"code": "EMPTY_TOPIC", "message": "请输入视频主题"})

    videos = await _generate_video_items(topic)
    content = _video_markdown(topic, videos)
    resource = _save_resource(
        enabled=req.save,
        student_id=req.student_id,
        resource_type="video_recommendation",
        title=f"教学视频推荐：{topic}",
        tags=[topic, "视频推荐", "队友成果集成"],
        content=content,
        ext="md",
        meta={"source": "teammate_video_generator", "videos": videos},
    )
    insert_learning_event(req.student_id, "multimodal_video", {"topic": topic, "saved": bool(resource)})
    return ApiResponse(request_id=request_id, success=True, data={"videos": videos, "content": content, "resource": resource})


@router.post("/video-search/stream")
async def video_search_stream(req: TopicRequest):
    request_id = new_id()

    async def work(on_chunk):
        topic = req.topic.strip()
        if not topic:
            raise ValueError("请输入视频主题")
        videos = await _generate_video_items(topic, on_chunk=on_chunk)
        content = _video_markdown(topic, videos)
        resource = _save_resource(
            enabled=req.save,
            student_id=req.student_id,
            resource_type="video_recommendation",
            title=f"教学视频推荐：{topic}",
            tags=[topic, "视频推荐", "队友成果集成"],
            content=content,
            ext="md",
            meta={"source": "teammate_video_generator", "videos": videos},
        )
        insert_learning_event(req.student_id, "multimodal_video", {"topic": topic, "saved": bool(resource)})
        return {"videos": videos, "content": content, "resource": resource}

    return stream_response(
        stream_live_operation(
            request_id=request_id,
            work=work,
            start_message="开始生成教学视频推荐",
            final_key="result",
            fallback_text=lambda result: result.get("content", ""),
            chunk_path="content",
        )
    )


@router.post("/code-case", response_model=ApiResponse)
async def code_case(req: CodeCaseRequest) -> ApiResponse:
    request_id = new_id()
    topic = req.topic.strip()
    if not topic:
        return ApiResponse(request_id=request_id, success=False, error={"code": "EMPTY_TOPIC", "message": "请输入实操主题"})

    content = await _generate_code_case(topic=topic, language=req.language.strip() or "Python")
    resource = _save_resource(
        enabled=req.save,
        student_id=req.student_id,
        resource_type="practice_case",
        title=f"代码实操案例：{topic}",
        tags=[topic, req.language, "队友成果集成"],
        content=content,
        ext="md",
        meta={"source": "teammate_code_agent", "language": req.language},
    )
    insert_learning_event(req.student_id, "multimodal_code", {"topic": topic, "language": req.language, "saved": bool(resource)})
    return ApiResponse(request_id=request_id, success=True, data={"content": content, "resource": resource})


@router.post("/code-case/stream")
async def code_case_stream(req: CodeCaseRequest):
    request_id = new_id()

    async def work(on_chunk):
        topic = req.topic.strip()
        if not topic:
            raise ValueError("请输入实操主题")
        content = await _generate_code_case(
            topic=topic,
            language=req.language.strip() or "Python",
            on_chunk=on_chunk,
        )
        resource = _save_resource(
            enabled=req.save,
            student_id=req.student_id,
            resource_type="practice_case",
            title=f"代码实操案例：{topic}",
            tags=[topic, req.language, "队友成果集成"],
            content=content,
            ext="md",
            meta={"source": "teammate_code_agent", "language": req.language},
        )
        insert_learning_event(req.student_id, "multimodal_code", {"topic": topic, "language": req.language, "saved": bool(resource)})
        return {"content": content, "resource": resource}

    return stream_response(
        stream_live_operation(
            request_id=request_id,
            work=work,
            start_message="开始生成代码实操案例",
            final_key="result",
            fallback_text=lambda result: result.get("content", ""),
            chunk_path="content",
        )
    )


@router.post("/voice-lesson", response_model=ApiResponse)
async def voice_lesson(req: VoiceLessonRequest) -> ApiResponse:
    request_id = new_id()
    topic = req.topic.strip()
    if not topic:
        return ApiResponse(request_id=request_id, success=False, error={"code": "EMPTY_TOPIC", "message": "请输入辅导主题"})

    content = await _generate_voice_plan(topic=topic, mode=req.mode)
    resource = _save_resource(
        enabled=req.save,
        student_id=req.student_id,
        resource_type="voice_tutor_plan",
        title=f"语音辅导方案：{topic}",
        tags=[topic, req.mode, "语音智能体"],
        content=content,
        ext="md",
        meta={"source": "teammate_voice_agent", "mode": req.mode},
    )
    insert_learning_event(req.student_id, "multimodal_voice", {"topic": topic, "mode": req.mode, "saved": bool(resource)})
    return ApiResponse(request_id=request_id, success=True, data={"content": content, "resource": resource})


@router.post("/voice-lesson/stream")
async def voice_lesson_stream(req: VoiceLessonRequest):
    request_id = new_id()

    async def work(on_chunk):
        topic = req.topic.strip()
        if not topic:
            raise ValueError("请输入辅导主题")
        content = await _generate_voice_plan(topic=topic, mode=req.mode, on_chunk=on_chunk)
        resource = _save_resource(
            enabled=req.save,
            student_id=req.student_id,
            resource_type="voice_tutor_plan",
            title=f"语音辅导方案：{topic}",
            tags=[topic, req.mode, "语音智能体"],
            content=content,
            ext="md",
            meta={"source": "teammate_voice_agent", "mode": req.mode},
        )
        insert_learning_event(req.student_id, "multimodal_voice", {"topic": topic, "mode": req.mode, "saved": bool(resource)})
        return {"content": content, "resource": resource}

    return stream_response(
        stream_live_operation(
            request_id=request_id,
            work=work,
            start_message="开始生成语音辅导方案",
            final_key="result",
            fallback_text=lambda result: result.get("content", ""),
            chunk_path="content",
        )
    )


async def _generate_video_items(
    topic: str,
    on_chunk: Callable[[str], Awaitable[None]] | None = None,
) -> list[dict]:
    platform_templates = [
        ("bilibili", "B站", "https://search.bilibili.com/all?keyword={}"),
        ("tencent", "腾讯视频", "https://v.qq.com/x/search/?q={}"),
        ("iqiyi", "爱奇艺", "https://so.iqiyi.com/so/q_{}"),
        ("youku", "优酷", "https://so.youku.com/search_video/q_{}"),
        ("xigua", "西瓜视频", "https://www.ixigua.com/search/{}?type=video"),
    ]

    if is_llm_configured("generate"):
        llm = get_llm_client_for("generate")
        try:
            data = await llm.chat_json(
                system="你是中国教育视频资源推荐专家。只推荐国内可访问的视频平台搜索词，不编造具体视频链接。",
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"围绕「{topic}」推荐 6 个教学视频搜索主题。"
                            "输出 JSON：{\"videos\":[{\"title\":\"...\",\"description\":\"...\",\"difficulty\":\"入门/进阶/高级\","
                            "\"duration_hint\":\"...\",\"keywords\":{\"bilibili\":\"...\",\"tencent\":\"...\",\"iqiyi\":\"...\",\"youku\":\"...\",\"xigua\":\"...\"}}]}"
                        ),
                    }
                ],
                schema_hint='{"videos":[{"title":"...","description":"...","difficulty":"...","duration_hint":"...","keywords":{"bilibili":"..."}}]}',
                on_chunk=on_chunk,
            )
            raw_videos = data.get("videos", []) if isinstance(data, dict) else []
        except Exception as exc:
            raise RuntimeError("视频推荐模型暂时不可用，本次没有生成固定推荐项，也没有写入伪资源") from exc
    else:
        raise RuntimeError("视频推荐模型尚未配置，本次没有生成固定推荐项，也没有写入伪资源")

    if not raw_videos:
        raise RuntimeError("视频推荐模型没有返回可用结果，本次没有生成固定推荐项，也没有写入伪资源")

    videos: list[dict] = []
    for item in raw_videos[:8]:
        keywords = item.get("keywords") or item.get("platform_search") or {}
        platforms = []
        for key, name, template in platform_templates:
            keyword = str(keywords.get(key) or item.get("title") or topic)
            platforms.append({"key": key, "name": name, "keyword": keyword, "url": template.format(quote(keyword))})
        videos.append(
            {
                "title": item.get("title") or f"{topic} 教学视频",
                "description": item.get("description") or "围绕当前主题的教学视频检索建议。",
                "difficulty": item.get("difficulty") or "入门",
                "duration_hint": item.get("duration_hint") or "",
                "platforms": platforms,
            }
        )
    return videos


async def _generate_code_case(
    topic: str,
    language: str,
    on_chunk: Callable[[str], Awaitable[None]] | None = None,
) -> str:
    if is_llm_configured("generate"):
        llm = get_llm_client_for("generate")
        try:
            return await llm.chat_text(
                system="你是代码实操案例智能体。输出中文 Markdown，代码块必须带语言标识，任务必须可复现。",
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"请为「{topic}」生成一份 {language} 代码实操案例。"
                            "必须包含：案例目标、适用学生、环境准备、3 个由易到难任务、完整示例代码、运行方式、"
                            "常见错误排查、验收标准、扩展挑战。"
                        ),
                    }
                ],
                temperature=0.45,
                max_tokens=1800,
                on_chunk=on_chunk,
            )
        except Exception as exc:
            raise RuntimeError("代码案例生成模型暂时不可用，本次没有生成模板案例，也没有写入伪资源") from exc

    raise RuntimeError("代码案例生成模型尚未配置，本次没有生成模板案例，也没有写入伪资源")


async def _generate_voice_plan(
    topic: str,
    mode: str,
    on_chunk: Callable[[str], Awaitable[None]] | None = None,
) -> str:
    mode_name = {
        "general": "通用答疑",
        "english": "英语学习",
        "interview": "面试辅导",
        "coding": "编程教学",
    }.get(mode, "通用答疑")

    if is_llm_configured("tutor"):
        llm = get_llm_client_for("tutor")
        try:
            return await llm.chat_text(
                system="你是语音教学智能体设计师。输出适合比赛演示的中文 Markdown 方案。",
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"请围绕「{topic}」设计一个「{mode_name}」语音辅导方案。"
                            "必须包含：开场话术、3 轮对话脚本、追问策略、朗读节奏、学生回答评价标准、"
                            "ASR/TTS/摄像头配置清单、异常处理方案；不得在模型不可用时编造本地脚本成果。"
                        ),
                    }
                ],
                temperature=0.45,
                on_chunk=on_chunk,
            )
        except Exception as exc:
            raise RuntimeError("语音辅导模型暂时不可用，本次没有生成模板脚本，也没有写入伪资源") from exc

    raise RuntimeError("语音辅导模型尚未配置，本次没有生成模板脚本，也没有写入伪资源")


def _video_markdown(topic: str, videos: list[dict]) -> str:
    lines = [f"# 教学视频推荐：{topic}", "", "## 推荐清单"]
    for idx, video in enumerate(videos, start=1):
        lines.extend(
            [
                "",
                f"### {idx}. {video['title']}",
                f"- 难度：{video.get('difficulty', '')}",
                f"- 建议时长：{video.get('duration_hint', '') or '按搜索结果选择'}",
                f"- 推荐理由：{video.get('description', '')}",
                "- 平台入口：",
            ]
        )
        for platform in video.get("platforms", []):
            lines.append(f"  - [{platform['name']}]({platform['url']})：{platform['keyword']}")
    lines.extend(["", "## 使用建议", "- 先看入门视频建立概念，再看案例视频完成迁移。", "- 每看完一个视频，记录 3 个关键词和 1 个仍然不懂的问题。"])
    return "\n".join(lines) + "\n"


def _save_resource(
    *,
    enabled: bool,
    student_id: str,
    resource_type: str,
    title: str,
    tags: list[str],
    content: str,
    ext: str,
    meta: dict,
) -> dict | None:
    if not enabled:
        return None
    file_id = new_id()
    rel_path = f"files/{student_id}/{file_id}.{ext}"
    path = settings.data_path / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return insert_resource_item(
        student_id=student_id,
        type=resource_type,
        title=title,
        tags=tags[:5],
        content_uri=rel_path.replace("\\", "/"),
        meta=meta,
    )
