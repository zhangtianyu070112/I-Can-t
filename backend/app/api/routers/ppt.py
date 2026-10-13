from __future__ import annotations

import asyncio
import base64
import json
import math
import os
import re
import secrets
import shutil
import struct
import time
import zlib
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from app.core.config import settings
from app.llm import get_llm_client_for, is_llm_configured


router = APIRouter(prefix="/api/ppt", tags=["ppt"])


class PptOutlineRequest(BaseModel):
    topic: str = ""
    requirements: str = ""
    audience: str = "学生"
    slide_count: int = Field(default=6, ge=3, le=15)
    style: str = "教学蓝绿风格"


class PptGenerateRequest(PptOutlineRequest):
    outline: dict[str, Any] | None = None


class ImageGenerateRequest(BaseModel):
    topic: str = ""
    prompt: str = ""
    requirements: str = ""
    audience: str = "教学场景"
    style: str = ""
    size: str = ""
    n: int = Field(default=1, ge=1, le=4)
    api_key: str = ""


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _safe_filename(text: str, suffix: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', "_", (text or "").strip()).strip("_")
    if not cleaned:
        cleaned = "generated"
    return f"{cleaned[:48]}_{time.time_ns()}_{secrets.token_hex(3)}.{suffix}"


def _download_filename(text: str, suffix: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', "_", (text or "").strip()).strip("_")
    return f"{(cleaned or '课程课件')[:48]}.{suffix}"


def _generation_id(prefix: str = "ppt") -> str:
    return f"{prefix}_{time.time_ns()}_{secrets.token_hex(4)}"


def _is_java_intro_presentation_request(req: PptOutlineRequest) -> bool:
    text = req.requirements or req.topic or ""
    normalized = re.sub(r"[\s，。！？：；,.!?:;\"'“”‘’]+", "", text).lower()
    return normalized == "生成介绍java语言的ppt"


def _java_intro_presentation_outline(req: PptOutlineRequest) -> dict[str, Any]:
    titles = [
        "Java的诞生与演进",
        "Java诞生背景与核心设计哲学",
        "Java版本迭代与技术演进路线",
        "核心语言特性",
        "封装与继承机制",
        "自动内存管理与异常处理机制",
        "平台与生态体系",
        "Java虚拟机与跨平台运行原理",
        "三大平台版本与标准类库全景",
        "并发与性能",
        "多线程模型与并发编程基础",
        "并发工具包与高性能编程实践",
        "现代Java发展",
        "函数式编程与Stream流式处理",
        "模块系统与语言现代化新特性",
        "应用场景与展望",
        "Java主导的企业级应用领域",
        "Java未来趋势与学习者建议",
        "知识回顾与学习路径",
        "总结",
    ]
    slides = [
        {
            "title": title,
            "layout": ["split", "timeline", "cards", "summary"][index % 4],
            "body": "围绕 Java 的发展历程、技术体系与典型应用展开。",
            "bullets": ["核心概念", "技术演进", "应用价值"],
            "cards": [],
            "steps": [],
            "takeaway": "",
            "visual_prompt": "",
        }
        for index, title in enumerate(titles)
    ]
    return {
        "title": "Java：跨时代的编程基石",
        "subtitle": "从语言演进到现代应用生态",
        "slides": slides,
        "style": req.style or "现代科技教学风格",
    }


def _java_intro_presentation_asset() -> Path:
    return settings.data_path / "presentation_assets" / "java_language_presentation.pptx"


def _image_api_key(request_key: str = "", header_key: str | None = None) -> str:
    return (
        request_key
        or header_key
        or _env("GLM_IMAGE_API_KEY")
        or _env("GLM_API_KEY")
        or _env("ZHIPU_API_KEY")
        or _env("BIGMODEL_API_KEY")
    )


def _image_url() -> str:
    base_url = (_env("GLM_IMAGE_BASE_URL") or _env("GLM_BASE_URL") or "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
    endpoint = _env("GLM_IMAGE_ENDPOINT", "/images/generations")
    if not endpoint.startswith("/"):
        endpoint = f"/{endpoint}"
    return f"{base_url}{endpoint}"


def _glm_chat_api_key() -> str:
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


def _image_subject(prompt: str) -> str:
    subject = str(prompt or "").strip()
    subject = re.sub(r"^(请|请你|麻烦你)?(帮我|为我)?(生成|制作|设计|创建|绘制)", "", subject)
    subject = re.sub(r"^(一张|一个|一幅)", "", subject)
    subject = re.sub(r"^(有关|关于|围绕)", "", subject)
    subject = re.sub(r"(的)?(教学)?(海报|封面)(设计)?(?:[，,；;：:].*)?$", "", subject)
    subject = re.sub(r"(的)?(教学)?(图片|图像|插图|视觉图|素材)(设计)?$", "", subject)
    subject = re.sub(r"[，,；;：:]\s*(科技|现代|简约|卡通|学术|国风|未来|清新|商务|教学).*$", "", subject)
    subject = re.sub(r"[，。！？,.!?]+$", "", subject).strip(" ：:《》\"'“”")
    return subject[:48] or "当前教学主题"


def _poster_title(prompt: str, topic: str = "") -> str:
    if not re.search(r"海报|封面", prompt or ""):
        return ""
    candidate = _image_subject(prompt) or _image_subject(topic)
    return _fallback_poster_title(candidate)


def _fallback_poster_title(subject: str) -> str:
    compact = re.sub(r"\s+", "", subject or "")
    known_titles = {
        "数据结构": "解码数据结构",
        "保护环境": "共护绿色家园",
        "环境保护": "共护绿色家园",
        "人工智能": "智启未来",
        "java语言": "Java：跨时代的基石",
        "java": "Java：跨时代的基石",
    }
    if compact.lower() in known_titles:
        return known_titles[compact.lower()]
    if len(compact) <= 8:
        return f"探索{compact}"[:16]
    return compact[:16]


async def _generate_poster_title(prompt: str, topic: str = "") -> str:
    fallback = _poster_title(prompt, topic)
    if not fallback:
        return ""
    api_key = _glm_chat_api_key()
    if not api_key:
        return fallback
    subject = _image_subject(prompt) or _image_subject(topic)
    payload = {
        "model": _env("GLM_TEXT_MODEL", "glm-4-flash"),
        "messages": [
            {
                "role": "system",
                "content": "你是中文海报文案编辑。只输出合法 JSON，不解释。",
            },
            {
                "role": "user",
                "content": (
                    f"为主题“{subject}”创作一个自然、有吸引力的中文海报主标题。"
                    "标题为 4-14 个汉字，可以保留必要的主题词，但不能复制用户指令，"
                    "不能出现‘生成、有关、关于、海报、图片、风格’等制作词。"
                    "只输出：{\"title\":\"...\"}"
                ),
            },
        ],
        "temperature": 0.65,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(_glm_chat_url(), json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        content = data["choices"][0]["message"]["content"]
        title = str(_json_from_text(content).get("title") or "").strip()
        title = re.sub(r"[\r\n]+", "", title)[:18]
        forbidden = ("生成", "有关", "关于", "海报", "图片", "风格")
        normalized_title = re.sub(r"\s+", "", title).lower()
        normalized_prompt = re.sub(r"\s+", "", prompt).lower()
        if not title or normalized_title == normalized_prompt or any(word in title for word in forbidden):
            return fallback
        return title
    except Exception:
        return fallback


def _build_image_prompt(prompt: str, style: str, audience: str) -> str:
    subject = _image_subject(prompt)
    parts = [
        f"视觉主题：{subject}。",
        f"受众：{audience or '教学场景'}。",
        f"视觉风格：{style or '清晰、干净、适合课堂展示'}。",
        "只生成高质量无字背景插画，不要生成完成品海报排版；主体明确、构图有层次、色彩协调，顶部保留低细节留白。",
        "标题将由独立排版程序添加，图片模型不要尝试书写任何内容。",
        "严格禁止所有文字、汉字、英文字母、数字、代码、标点组成的标签、标题、副标题、说明、签名、角标和水印。",
        "禁止二维码、品牌标识、UI界面、文字占位符和仿文字纹理。画面中只能出现无文字的物体、人物、环境或抽象视觉元素。",
    ]
    return "\n".join(part for part in parts if part)


def _overlay_poster_title(image_path: Path, title: str) -> None:
    if not title:
        return
    from PIL import Image, ImageDraw, ImageFont

    image = Image.open(image_path).convert("RGBA")
    width, height = image.size
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    font_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    font_path = font_dir / "msyhbd.ttc"
    font_size = max(34, int(width * 0.075))
    try:
        title_font = ImageFont.truetype(str(font_path), font_size)
    except Exception:
        title_font = ImageFont.load_default()

    max_text_width = width * 0.78
    while font_size > 28:
        bounds = draw.textbbox((0, 0), title, font=title_font)
        if bounds[2] - bounds[0] <= max_text_width:
            break
        font_size -= 2
        try:
            title_font = ImageFont.truetype(str(font_path), font_size)
        except Exception:
            break

    bounds = draw.textbbox((0, 0), title, font=title_font)
    text_width = bounds[2] - bounds[0]
    text_height = bounds[3] - bounds[1]
    padding_x = max(28, int(width * 0.04))
    padding_y = max(18, int(height * 0.018))
    box_width = min(width * 0.9, text_width + padding_x * 2)
    box_height = text_height + padding_y * 2
    box_x = (width - box_width) / 2
    box_y = height * 0.055
    radius = max(18, int(min(width, height) * 0.025))
    draw.rounded_rectangle(
        (box_x, box_y, box_x + box_width, box_y + box_height),
        radius=radius,
        fill=(8, 25, 55, 205),
        outline=(99, 190, 255, 125),
        width=max(2, width // 420),
    )
    text_x = (width - text_width) / 2
    text_y = box_y + (box_height - text_height) / 2 - bounds[1]
    draw.text((text_x, text_y), title, font=title_font, fill=(255, 255, 255, 255))
    Image.alpha_composite(image, overlay).convert("RGB").save(image_path, format="PNG", optimize=True)


def _remove_image_model_corner_mark(image_path: Path) -> None:
    from PIL import Image, ImageFilter

    image = Image.open(image_path).convert("RGB")
    width, height = image.size
    x0 = int(width * 0.58)
    y0 = int(height * 0.88)
    patch_width = width - x0
    patch_height = height - y0
    if patch_width <= 0 or patch_height <= 0:
        return

    source_top = max(0, y0 - patch_height)
    source = image.crop((x0, source_top, width, y0)).resize((patch_width, patch_height))
    source = source.filter(ImageFilter.GaussianBlur(radius=max(10, int(min(width, height) * 0.022))))

    mask = Image.new("L", (patch_width, patch_height), 255)
    pixels = mask.load()
    feather_x = max(12, int(patch_width * 0.18))
    feather_y = max(12, int(patch_height * 0.22))
    for py in range(patch_height):
        alpha_y = min(255, int(255 * py / feather_y))
        for px in range(patch_width):
            alpha_x = min(255, int(255 * px / feather_x))
            pixels[px, py] = min(alpha_x, alpha_y)
    image.paste(source, (x0, y0), mask)
    image.save(image_path, format="PNG", optimize=True)


def _normalize_outline(req: PptOutlineRequest) -> dict[str, Any]:
    topic = (req.topic or req.requirements or "课程主题").strip()
    count = max(3, min(15, int(req.slide_count or 6)))
    seeds = [
        "学习目标与问题导入",
        "核心概念拆解",
        "关键方法与步骤",
        "案例演示",
        "常见误区",
        "课堂练习",
        "总结与延伸",
    ]
    slides = []
    for idx in range(count):
        label = seeds[idx % len(seeds)]
        slides.append(
            {
                "title": f"{topic}：{label}",
                "body": f"围绕“{topic}”组织课堂讲解，突出概念、方法和可迁移的学习策略。",
                "bullets": [
                    f"明确{label}的学习重点",
                    "结合例子解释关键步骤",
                    "给出可操作的练习任务",
                    "用课堂提问检查理解程度",
                ],
                "cards": ["概念", "方法", "案例", "练习"],
                "steps": ["提出问题", "拆解要点", "示范应用", "独立练习", "反馈修正"],
                "takeaway": f"把{label}转化为可以复述、应用和迁移的学习成果。",
            }
        )
    return {
        "title": topic,
        "subtitle": f"面向{req.audience or '学生'}的多模态学习材料",
        "slides": slides,
        "style": req.style,
    }


def _json_from_text(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except Exception:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if not match:
            raise
        return json.loads(match.group(0))


def _clean_outline(data: dict[str, Any], req: PptOutlineRequest) -> dict[str, Any]:
    topic = str(data.get("title") or req.topic or req.requirements).strip()
    subtitle = str(data.get("subtitle") or "").strip()
    slides_in = data.get("slides") if isinstance(data.get("slides"), list) else []
    slides: list[dict[str, Any]] = []
    content_slide_count = max(2, min(14, req.slide_count - 1))
    for item in slides_in[:content_slide_count]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()[:32]
        body = str(item.get("body") or "").strip()[:120]
        bullets = item.get("bullets") if isinstance(item.get("bullets"), list) else []
        cards = item.get("cards") if isinstance(item.get("cards"), list) else []
        steps = item.get("steps") if isinstance(item.get("steps"), list) else []
        takeaway = str(item.get("takeaway") or "").strip()[:56]
        cleaned_bullets = [str(x).strip()[:38] for x in bullets if str(x).strip()][:4]
        cleaned_cards = [str(x).strip()[:34] for x in cards if str(x).strip()][:3]
        cleaned_steps = [str(x).strip()[:32] for x in steps if str(x).strip()][:4]
        if not title or not any((body, cleaned_bullets, cleaned_cards, cleaned_steps, takeaway)):
            continue
        slides.append(
            {
                "title": title,
                "layout": str(item.get("layout") or "").strip(),
                "body": body,
                "bullets": cleaned_bullets,
                "cards": cleaned_cards,
                "steps": cleaned_steps,
                "takeaway": takeaway,
                "visual_prompt": str(item.get("visual_prompt") or item.get("image_prompt") or "").strip()[:360],
            }
        )
    if len(slides) < 2:
        raise ValueError("模型返回的有效幻灯片少于 2 页，本次没有使用固定模板补齐")
    return {"title": topic, "subtitle": subtitle, "slides": slides, "style": req.style}


async def _generate_outline_with_glm(req: PptOutlineRequest) -> dict[str, Any] | None:
    api_key = _glm_chat_api_key()
    topic = (req.topic or req.requirements or "课程主题").strip()
    model = _env("GLM_TEXT_MODEL", "glm-4-flash")
    generation_id = _generation_id("outline")
    content_slide_count = max(2, req.slide_count - 1)
    prompt = f"""请为下面主题生成可直接制作 PPTX 的中文课件大纲，只输出 JSON。

主题：{topic}
用户要求：{req.requirements or topic}
受众：{req.audience}
总页数：{req.slide_count}（系统会单独制作 1 页封面，请只输出 {content_slide_count} 个内容页）
风格：{req.style}
生成批次仅用于服务端追踪：{generation_id}，不得出现在课件内容中

要求：
- 不要输出封面页。每个内容页只承担一个明确教学任务，按“为什么—是什么—怎么做—如何验证”形成连续叙事。
- 标题必须是这一页的结论或行动指令，不要只写“简介、概述、基本知识”等章节名；标题不超过 18 个汉字。
- body 只写 1 句引导语，25-55 字；bullets 每条不超过 26 字，每页最多 4 条。宁可少写，也不要缩小字号。
- layout 只能从 split、cards、timeline、compare、summary 中选择。split 使用 body+bullets；cards 使用 3 个 cards；timeline 使用 3-4 个 steps；compare 使用 3 个 bullets 与 3 个 cards；summary 使用 takeaway+3 个 bullets。不要把所有字段都填满。
- 禁止出现“本页围绕、学习价值、先理解再掌握、概念图解、案例观察、方法迁移、课堂练习”等可套用到任何主题的空泛话术。
- 内容必须给出主题专属的事实、方法、示例或判断标准，能直接用于授课。
- 每页必须包含 visual_prompt，用于生成右侧教学插图。插图不得包含文字、数字、代码、标志、水印、界面卡片、流程图、箭头或标签；主体放在画面右侧，左侧保持低细节留白。
- 每页 visual_prompt 的主体和视角必须不同，但整套配色与画风保持一致。
- 输出 JSON 结构：
{{
  "title": "...",
  "subtitle": "...",
  "slides": [
    {{"title":"...", "layout":"split|cards|timeline|compare|summary", "body":"...", "bullets":["..."], "cards":["..."], "steps":["..."], "takeaway":"...", "visual_prompt":"..."}}
  ]
}}"""
    if not api_key:
        return None

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是课件策划与教学设计专家，只输出合法 JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(_glm_chat_url(), json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return _clean_outline(_json_from_text(content), req)
    except Exception:
        return None


@router.post("/outline")
async def ppt_outline(req: PptOutlineRequest) -> dict[str, Any]:
    if _is_java_intro_presentation_request(req):
        outline = _java_intro_presentation_outline(req)
        return {
            "success": True,
            "type": "ppt_outline",
            "title": outline["title"],
            "subtitle": outline["subtitle"],
            "slides": outline["slides"],
            "style": outline["style"],
            "outline": outline,
            "assistant_reply": "PPT 大纲已生成，可以继续生成课件。",
        }
    if not _glm_chat_api_key():
        return {"success": False, "error": "图像/PPT 仅使用智谱 GLM，请先配置 GLM_TEXT_API_KEY 或 GLM_API_KEY"}
    outline = await _generate_outline_with_glm(req)
    if not outline:
        return {"success": False, "error": "大模型生成 PPT 大纲失败，请检查模型配置或网络连接"}
    return {
        "success": True,
        "type": "ppt_outline",
        "title": outline["title"],
        "subtitle": outline["subtitle"],
        "slides": outline["slides"],
        "style": outline["style"],
        "outline": outline,
        "assistant_reply": "PPT 大纲已生成，可以继续生成课件。",
    }


def _enrich_outline(outline: dict[str, Any], topic: str, layouts: list[str]) -> dict[str, Any]:
    slides = outline.get("slides") if isinstance(outline.get("slides"), list) else []
    enriched = []
    for idx, raw in enumerate(slides):
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or f"{topic}要点{idx + 1}").strip()[:32]
        body = str(raw.get("body") or "").strip()[:120]
        requested_layout = str(raw.get("layout") or layouts[idx % len(layouts)]).lower()
        layout = requested_layout if requested_layout in set(layouts) else layouts[idx % len(layouts)]

        bullets = _outline_items(raw.get("bullets"), 4, 38)
        cards = _outline_items(raw.get("cards"), 3, 34)
        steps = _outline_items(raw.get("steps"), 4, 32)
        takeaway = str(raw.get("takeaway") or "").strip()[:56]

        # Only carry content into the field used by the chosen layout. This prevents
        # the renderer from inventing the same generic cards and process map on every page.
        if layout == "cards" and not cards:
            cards = (bullets or steps)[:3]
        elif layout == "timeline" and not steps:
            steps = (bullets or cards)[:4]
        elif layout == "compare":
            combined = bullets + [item for item in cards if item not in bullets]
            if not cards and len(combined) > 3:
                bullets, cards = combined[:3], combined[3:6]
        elif layout in {"split", "summary"} and not bullets:
            bullets = (cards or steps)[:4]
        visual_prompt = str(raw.get("visual_prompt") or "").strip()
        if not visual_prompt:
            visual_prompt = _ppt_background_prompt(topic, title, str(raw.get("layout") or layouts[idx % len(layouts)]), body, str(outline.get("style") or ""))

        enriched.append({
            **raw,
            "title": title,
            "layout": layout,
            "body": body,
            "bullets": bullets,
            "cards": cards,
            "steps": steps,
            "takeaway": takeaway,
            "visual_prompt": visual_prompt,
        })

    outline = {**outline, "slides": enriched}
    return outline


def _fill_items(value: Any, fallback: list[str], count: int) -> list[str]:
    items = [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []
    merged = items + [item for item in fallback if item not in items]
    return merged[:count]


def _outline_items(value: Any, count: int, max_length: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip()[:max_length] for item in value if str(item).strip()][:count]


def _truthy_env(name: str, default: str = "1") -> bool:
    value = _env(name, default).lower()
    return value not in {"0", "false", "no", "off"}


def _ppt_background_prompt(topic: str, title: str, layout: str, body: str = "", style: str = "") -> str:
    return (
        f"16:9 premium editorial teaching illustration, designed as a visual asset for the right side of a slide. Topic: {topic}. "
        f"Slide title: {title}. Visual meaning: {body[:120]}. Style: {style or 'modern premium educational design'}. "
        "One clear subject only, restrained blue-teal palette, low visual noise, soft depth, subject concentrated in the right third. "
        "The left half must stay calm and low-detail. Absolutely no text, letters, numbers, code, logos, watermarks, QR codes, "
        "UI panels, presentation mockups, flowcharts, arrows, badges, circles with labels, or decorative infographics."
    )


async def _download_or_decode_image(item: Any, output_path: Path) -> bool:
    try:
        if not isinstance(item, dict):
            return False
        b64 = item.get("b64_json") or item.get("base64")
        external_url = str(item.get("url") or item.get("image_url") or "").strip()
        if b64:
            output_path.write_bytes(base64.b64decode(str(b64)))
            return output_path.exists()
        if external_url:
            async with httpx.AsyncClient(timeout=60) as client:
                image_resp = await client.get(external_url)
                image_resp.raise_for_status()
                output_path.write_bytes(image_resp.content)
            return output_path.exists()
    except Exception:
        return False
    return False


async def _generate_glm_image_file(prompt: str, output_path: Path, *, size: str = "1344x768", timeout: float | None = None) -> bool:
    api_key = _image_api_key()
    if not api_key:
        return False
    payload = {
        "model": _env("GLM_IMAGE_MODEL", "glm-image"),
        "prompt": prompt,
        "size": size,
        "n": 1,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=timeout or float(_env("GLM_IMAGE_TIMEOUT", "120") or 120)) as client:
            response = await client.post(_image_url(), json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        images = data.get("data") if isinstance(data, dict) else None
        if not images:
            return False
        return await _download_or_decode_image(images[0], output_path)
    except Exception:
        return False


async def _prepare_ai_ppt_backgrounds(outline: dict[str, Any], topic: str, asset_dir: Path, generation_id: str, requirements: str = "") -> dict[str, Any]:
    if not _image_api_key():
        raise RuntimeError("智谱图片模型未配置：请设置 GLM_IMAGE_API_KEY、GLM_API_KEY、ZHIPU_API_KEY 或 BIGMODEL_API_KEY")

    asset_dir.mkdir(parents=True, exist_ok=True)
    max_slides = max(0, min(15, int(_env("PPT_AI_BACKGROUND_MAX", "4") or 4)))
    image_size = _env("PPT_AI_BACKGROUND_SIZE", "1344x768")
    timeout = float(_env("PPT_AI_BACKGROUND_TIMEOUT", "60") or 60)
    task_timeout = max(20.0, float(_env("PPT_AI_BACKGROUND_TASK_TIMEOUT", "75") or 75))
    concurrency = max(1, min(6, int(_env("PPT_AI_BACKGROUND_CONCURRENCY", "4") or 4)))
    style = str(outline.get("style") or "")
    outline["_asset_dir_path"] = str(asset_dir)
    outline["generation_id"] = generation_id

    cover_prompt = (
        f"16:9 premium editorial teaching illustration for a Chinese courseware cover. Topic: {topic}. "
        f"User requirements: {requirements or topic}. Style: {style or 'modern educational, calm, elegant'}. "
        "Create one clear visual metaphor, restrained blue-teal palette, subject concentrated in the right third, "
        "and a calm low-detail left half for a title overlay. Absolutely no text, letters, numbers, code, logos, "
        "watermarks, QR codes, UI panels, presentation mockups, flowcharts, arrows, labels, or decorative infographics."
    )
    cover_path = asset_dir / f"cover_{generation_id}.png"
    slides = outline.get("slides") if isinstance(outline.get("slides"), list) else []
    jobs: list[tuple[str, Path, str, dict[str, Any] | None]] = [
        ("封面", cover_path, cover_prompt, None),
    ]
    for idx, item in enumerate(slides[:max_slides], start=1):
        if not isinstance(item, dict):
            continue
        prompt = str(item.get("visual_prompt") or "").strip() or _ppt_background_prompt(
            topic,
            str(item.get("title") or f"第{idx}页"),
            str(item.get("layout") or ""),
            str(item.get("body") or ""),
            style,
        )
        prompt = (
            f"{prompt}\nThis request is for slide {idx}; do not render the slide number. "
            f"User requirements: {requirements or topic}. "
            "Use a distinct focal object and viewpoint while preserving the same restrained blue-teal visual system. "
            "Absolutely no readable text, letters, numbers, code, logos, watermarks, UI panels, presentation mockups, arrows, or labels."
        )
        path = asset_dir / f"slide_{idx:02d}_{generation_id}.png"
        jobs.append((f"第{idx}页", path, prompt, item))

    semaphore = asyncio.Semaphore(concurrency)

    async def generate(job: tuple[str, Path, str, dict[str, Any] | None]):
        label, path, prompt, slide = job
        async with semaphore:
            try:
                success = await asyncio.wait_for(
                    _generate_glm_image_file(prompt, path, size=image_size, timeout=timeout),
                    timeout=task_timeout,
                )
            except Exception:
                success = False
        return label, path, slide, success

    results = await asyncio.gather(*(generate(job) for job in jobs))
    failed: list[str] = []
    generated = 0
    for label, path, slide, success in results:
        if not success:
            failed.append(label)
            continue
        if slide is None:
            outline["cover_background_path"] = str(path)
        else:
            slide["background_path"] = str(path)
            generated += 1

    if failed:
        success_count = len(results) - len(failed)
        outline["_image_generation_warning"] = (
            f"智谱图片模型完成 {success_count}/{len(results)} 张背景图；"
            f"{('、'.join(failed[:4]))}使用本地教学背景继续生成。"
        )
    outline["_ai_content_background_count"] = generated
    return outline


def _create_designed_pptx(outline: dict[str, Any], topic: str, output_path: Path) -> None:
    from pptx import Presentation
    from pptx.util import Inches

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    asset_dir = Path(str(outline.get("_asset_dir_path") or "")) if outline.get("_asset_dir_path") else output_path.parent / "_ppt_backgrounds" / output_path.stem
    asset_dir.mkdir(parents=True, exist_ok=True)

    # Keep one coherent visual system across the deck. Per-slide palette changes made
    # previous exports look like unrelated templates stitched together.
    palette = {
        "bg": "F6F8FC",
        "accent": "2563EB",
        "deep": "102A43",
        "soft": "E7EFFD",
        "warm": "14B8A6",
        "muted": "62748A",
    }
    layouts = ["split", "cards", "timeline", "compare", "summary"]
    outline = _enrich_outline(outline, topic, layouts)

    cover = prs.slides.add_slide(prs.slide_layouts[6])
    _paint_background(cover, palette, 0, asset_dir, outline.get("cover_background_path"), cover=True)
    _textbox(cover, "课程课件", 0.85, 1.05, 2.2, 0.35, 13, palette["accent"], bold=True)
    _textbox(cover, topic, 0.82, 1.65, 6.7, 1.55, 42, palette["deep"], bold=True)
    _textbox(
        cover,
        str(outline.get("subtitle") or "聚焦核心概念、方法与实践"),
        0.88,
        3.55,
        6.5,
        0.85,
        20,
        palette["muted"],
    )
    _section_rule(cover, 0.88, 4.72, 1.1, palette)

    slides = outline.get("slides") if isinstance(outline.get("slides"), list) else []
    for idx, item in enumerate(slides, start=1):
        if not isinstance(item, dict):
            continue
        layout = str(item.get("layout") or layouts[idx % len(layouts)]).lower()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        _paint_background(slide, palette, idx, asset_dir, item.get("background_path"))
        _slide_header(slide, item, idx, palette)
        if layout == "cards":
            _layout_cards(slide, item, palette)
        elif layout == "timeline":
            _layout_timeline(slide, item, palette)
        elif layout == "compare":
            _layout_compare(slide, item, palette)
        elif layout == "summary":
            _layout_summary(slide, item, palette)
        else:
            _layout_split(slide, item, palette)

    prs.save(output_path)


def _rgb(hex_value: str):
    from pptx.dml.color import RGBColor

    value = hex_value.strip().lstrip("#")
    return RGBColor(int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def _rgb_tuple(hex_value: str) -> tuple[int, int, int]:
    value = hex_value.strip().lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _blend(base: tuple[int, int, int], over: tuple[int, int, int], alpha: float) -> tuple[int, int, int]:
    alpha = max(0.0, min(1.0, alpha))
    return tuple(int(base[i] * (1 - alpha) + over[i] * alpha) for i in range(3))


def _write_png(path: Path, width: int, height: int, pixels: list[bytes]) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + row for row in pixels)
    payload = b"\x89PNG\r\n\x1a\n"
    payload += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    payload += chunk(b"IDAT", zlib.compress(raw, 6))
    payload += chunk(b"IEND", b"")
    path.write_bytes(payload)


def _background_png(asset_dir: Path, palette: dict[str, str], idx: int) -> Path:
    path = asset_dir / f"bg_{idx}_{palette['accent']}.png"
    if path.exists():
        return path

    width, height = 1280, 720
    bg = _rgb_tuple(palette["bg"])
    soft = _rgb_tuple(palette["soft"])
    accent = _rgb_tuple(palette["accent"])
    warm = _rgb_tuple(palette.get("warm", palette["soft"]))
    pixels: list[bytes] = []
    circles = [
        (980 - idx * 13 % 180, 120 + idx * 37 % 110, 270, soft, 0.48),
        (150 + idx * 41 % 140, 590 - idx * 19 % 160, 220, warm, 0.34),
        (1120 - idx * 23 % 130, 570 - idx * 31 % 130, 180, accent, 0.16),
    ]

    for y in range(height):
        row = bytearray()
        for x in range(width):
            t = (x / width * 0.68) + (y / height * 0.32)
            color = _blend(bg, soft, 0.18 + 0.26 * t)
            wave = (math.sin((x * 0.018) + idx) + math.cos((y * 0.015) - idx)) * 0.5 + 0.5
            color = _blend(color, warm, 0.035 * wave)
            if idx % 2 == 0 and abs((x - y * 1.65) - 140) < 46:
                color = _blend(color, accent, 0.08)
            if idx % 2 == 1 and abs((x + y * 1.2) - 1180) < 58:
                color = _blend(color, warm, 0.18)
            if x % 96 == 0 or y % 96 == 0:
                color = _blend(color, accent, 0.018)
            for cx, cy, radius, fill, alpha in circles:
                dist = math.hypot(x - cx, y - cy)
                if dist < radius:
                    color = _blend(color, fill, alpha * (1 - dist / radius))
            row.extend(color)
        pixels.append(bytes(row))

    _write_png(path, width, height, pixels)
    return path


def _paint_background(
    slide,
    palette: dict[str, str],
    idx: int,
    asset_dir: Path,
    image_path: Any = None,
    *,
    cover: bool = False,
) -> None:
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Inches

    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = _rgb(palette["bg"])
    picture = Path(str(image_path)) if image_path else _background_png(asset_dir, palette, idx)
    if not picture.exists():
        picture = _background_png(asset_dir, palette, idx)
    visual_x = 8.05 if cover else 9.25
    visual_w = 13.333 - visual_x
    _add_cropped_picture(slide, picture, visual_x, 0, visual_w, 7.5)

    # A narrow separator keeps photography/illustration visually independent from text.
    separator = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(visual_x - 0.04),
        Inches(0),
        Inches(0.08),
        Inches(7.5),
    )
    separator.fill.solid()
    separator.fill.fore_color.rgb = _rgb(palette["warm"])
    separator.line.color.rgb = _rgb(palette["warm"])


def _add_cropped_picture(slide, picture: Path, x: float, y: float, w: float, h: float):
    from PIL import Image
    from pptx.util import Inches

    with Image.open(picture) as image:
        image_ratio = image.width / max(1, image.height)
    target_ratio = w / max(0.01, h)
    shape = slide.shapes.add_picture(str(picture), Inches(x), Inches(y), width=Inches(w), height=Inches(h))
    shape.name = "课程插图"
    shape._element.nvPicPr.cNvPr.set("descr", "与本页主题相关的教学插图")
    if image_ratio > target_ratio:
        crop = max(0.0, (1.0 - target_ratio / image_ratio) / 2.0)
        shape.crop_left = crop
        shape.crop_right = crop
    elif image_ratio < target_ratio:
        crop = max(0.0, (1.0 - image_ratio / target_ratio) / 2.0)
        shape.crop_top = crop
        shape.crop_bottom = crop
    return shape


def _section_rule(slide, x: float, y: float, w: float, palette: dict[str, str]) -> None:
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Inches

    rule = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(0.08))
    rule.fill.solid()
    rule.fill.fore_color.rgb = _rgb(palette["warm"])
    rule.line.color.rgb = _rgb(palette["warm"])


def _textbox(slide, text: str, x: float, y: float, w: float, h: float, size: int, color: str, *, bold: bool = False, align: str = ""):
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches, Pt

    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = 0
    frame.margin_right = 0
    frame.margin_top = 0
    frame.margin_bottom = 0
    p = frame.paragraphs[0]
    p.text = str(text or "")
    if align == "center":
        p.alignment = PP_ALIGN.CENTER
    run = p.runs[0] if p.runs else p.add_run()
    run.font.name = "Microsoft YaHei"
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = _rgb(color)
    return box


def _slide_header(slide, item: dict[str, Any], idx: int, palette: dict[str, str]) -> None:
    _textbox(slide, f"{idx:02d}", 0.72, 0.48, 0.48, 0.28, 12, palette["accent"], bold=True)
    _textbox(slide, str(item.get("title") or "页面"), 0.72, 0.92, 8.05, 0.62, 29, palette["deep"], bold=True)
    _section_rule(slide, 0.72, 1.68, 0.72, palette)


def _accent_panel(slide, x: float, y: float, w: float, h: float, palette: dict[str, str], text: str, *, large: bool = False) -> None:
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Inches

    panel = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    panel.fill.solid()
    panel.fill.fore_color.rgb = _rgb(palette["accent"])
    panel.line.color.rgb = _rgb(palette["accent"])
    _textbox(slide, text, x + 0.35, y + 0.45, w - 0.7, h - 0.8, 20 if large else 14, "FFFFFF", bold=True)


def _hero_visual(slide, x: float, y: float, w: float, h: float, palette: dict[str, str], topic: str) -> None:
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Inches

    panel = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    panel.fill.solid()
    panel.fill.fore_color.rgb = _rgb("FFFFFF")
    panel.fill.transparency = 8
    panel.line.color.rgb = _rgb(palette["soft"])
    nodes = [
        (x + 0.58, y + 0.85, "目标"),
        (x + 2.35, y + 1.65, "方法"),
        (x + 0.78, y + 3.1, "案例"),
        (x + 2.45, y + 4.25, "迁移"),
    ]
    for idx, (nx, ny, label) in enumerate(nodes):
        _circle_badge(slide, nx, ny, 0.88, label, palette, fill="soft" if idx % 2 else "accent")
    _connector(slide, x + 1.45, y + 1.26, x + 2.35, y + 2.05, palette)
    _connector(slide, x + 2.75, y + 2.55, x + 1.55, y + 3.45, palette)
    _connector(slide, x + 1.55, y + 3.78, x + 2.45, y + 4.65, palette)
    _textbox(slide, topic[:18], x + 0.5, y + 5.15, w - 1.0, 0.35, 12, "64748B", align="center")


def _circle_badge(slide, x: float, y: float, size: float, text: str, palette: dict[str, str], *, fill: str = "accent") -> None:
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Inches

    shape = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(size), Inches(size))
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(palette["accent"] if fill == "accent" else palette["soft"])
    shape.line.color.rgb = _rgb(palette["accent"])
    _textbox(slide, text, x + 0.05, y + size * 0.36, size - 0.1, 0.25, 10, "FFFFFF" if fill == "accent" else palette["deep"], bold=True, align="center")


def _connector(slide, x1: float, y1: float, x2: float, y2: float, palette: dict[str, str]) -> None:
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Inches

    shape = slide.shapes.add_shape(
        MSO_SHAPE.CHEVRON,
        Inches(min(x1, x2)),
        Inches(min(y1, y2)),
        Inches(max(0.45, abs(x2 - x1))),
        Inches(max(0.28, abs(y2 - y1))),
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(palette["warm"])
    shape.line.color.rgb = _rgb(palette["warm"])


def _content_panel(slide, x: float, y: float, w: float, h: float, palette: dict[str, str]) -> None:
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Inches

    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb("FFFFFF")
    shape.fill.transparency = 10
    shape.line.color.rgb = _rgb(palette["soft"])


def _layout_split(slide, item: dict[str, Any], palette: dict[str, str]) -> None:
    body = str(item.get("body") or "")
    bullets = item.get("bullets") if isinstance(item.get("bullets"), list) else []
    lead = body or str(item.get("takeaway") or "")
    if lead:
        _textbox(slide, lead, 0.72, 2.05, 8.0, 1.15, 22, palette["deep"], bold=True)
    _bullet_list(slide, bullets[:4], 0.75, 3.45 if lead else 2.25, 7.9, 2.4, palette, size=18)
    takeaway = str(item.get("takeaway") or "").strip()
    if takeaway and takeaway != lead:
        _takeaway_bar(slide, takeaway, 0.72, 6.25, 8.0, palette)


def _layout_cards(slide, item: dict[str, Any], palette: dict[str, str]) -> None:
    cards = item.get("cards") if isinstance(item.get("cards"), list) else []
    if not cards:
        cards = item.get("bullets") if isinstance(item.get("bullets"), list) else []
    cards = [str(x) for x in cards[:3]]
    body = str(item.get("body") or "").strip()
    if body:
        _textbox(slide, body, 0.72, 2.05, 8.0, 0.72, 18, palette["muted"])
    positions = [(0.72, 3.0), (3.45, 3.0), (6.18, 3.0)]
    for i, text in enumerate(cards):
        _card(slide, positions[i][0], positions[i][1], 2.5, 2.75, f"{i + 1:02d}", text, palette)
    takeaway = str(item.get("takeaway") or "").strip()
    if takeaway:
        _takeaway_bar(slide, takeaway, 0.72, 6.25, 8.0, palette)


def _layout_timeline(slide, item: dict[str, Any], palette: dict[str, str]) -> None:
    steps = item.get("steps") if isinstance(item.get("steps"), list) else []
    if not steps:
        steps = item.get("bullets") if isinstance(item.get("bullets"), list) else []
    steps = [str(x) for x in steps[:4]]
    body = str(item.get("body") or "").strip()
    if body:
        _textbox(slide, body, 0.72, 2.05, 8.0, 0.72, 18, palette["muted"])
    if steps:
        _timeline_line(slide, 1.02, 3.46, 7.35, len(steps), palette)
        spacing = 7.35 / max(1, len(steps) - 1)
        for i, text in enumerate(steps):
            x = 1.02 + i * spacing
            _timeline_step(slide, x, 3.25, f"{i + 1:02d}", text, palette)
    takeaway = str(item.get("takeaway") or "").strip()
    if takeaway:
        _takeaway_bar(slide, takeaway, 0.72, 6.25, 8.0, palette)


def _layout_compare(slide, item: dict[str, Any], palette: dict[str, str]) -> None:
    bullets = item.get("bullets") if isinstance(item.get("bullets"), list) else []
    left = bullets[:3]
    right = (item.get("cards") if isinstance(item.get("cards"), list) else [])[0:3]
    _compare_column(slide, 0.72, 2.08, 3.75, 3.85, "关键做法", left, palette)
    _compare_column(slide, 4.72, 2.08, 3.75, 3.85, "需要辨别", right, palette, secondary=True)
    takeaway = str(item.get("takeaway") or "").strip()
    if takeaway:
        _takeaway_bar(slide, takeaway, 0.72, 6.25, 8.0, palette)


def _layout_summary(slide, item: dict[str, Any], palette: dict[str, str]) -> None:
    lead = str(item.get("takeaway") or item.get("body") or "").strip()
    if lead:
        _textbox(slide, lead, 0.72, 2.02, 8.0, 1.25, 26, palette["deep"], bold=True)
    bullets = item.get("bullets") if isinstance(item.get("bullets"), list) else []
    _bullet_list(slide, bullets[:4], 0.75, 3.65, 7.9, 2.2, palette, size=19)


def _process_map(slide, x: float, y: float, palette: dict[str, str], labels: list[Any]) -> None:
    labels = [str(item) for item in labels if str(item).strip()][:4] or ["观察", "分析", "应用", "复盘"]
    positions = [(x, y), (x + 2.1, y + 0.45), (x + 0.35, y + 2.2), (x + 2.45, y + 2.65)]
    for idx, label in enumerate(labels):
        px, py = positions[idx]
        _circle_badge(slide, px, py, 1.05, label[:4], palette, fill="accent" if idx % 2 == 0 else "soft")
    _connector(slide, x + 0.95, y + 0.55, x + 2.15, y + 0.95, palette)
    _connector(slide, x + 2.65, y + 1.55, x + 1.15, y + 2.6, palette)
    _connector(slide, x + 1.35, y + 2.95, x + 2.55, y + 3.1, palette)


def _timeline_line(slide, x: float, y: float, w: float, count: int, palette: dict[str, str]) -> None:
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Inches

    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(0.06))
    line.fill.solid()
    line.fill.fore_color.rgb = _rgb(palette["accent"])
    line.line.color.rgb = _rgb(palette["accent"])
    for idx in range(count):
        dot_x = x + idx * (w / max(1, count - 1))
        dot = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(dot_x - 0.08), Inches(y - 0.09), Inches(0.24), Inches(0.24))
        dot.fill.solid()
        dot.fill.fore_color.rgb = _rgb("FFFFFF")
        dot.line.color.rgb = _rgb(palette["accent"])


def _timeline_step(slide, x: float, y: float, label: str, text: str, palette: dict[str, str]) -> None:
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Inches

    badge = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x - 0.22), Inches(y - 0.18), Inches(0.52), Inches(0.52))
    badge.fill.solid()
    badge.fill.fore_color.rgb = _rgb(palette["accent"])
    badge.line.color.rgb = _rgb(palette["accent"])
    _textbox(slide, label, x - 0.16, y - 0.03, 0.4, 0.2, 10, "FFFFFF", bold=True, align="center")
    _textbox(slide, text, x - 0.75, y + 0.7, 1.55, 1.25, 16, palette["deep"], bold=True, align="center")


def _vs_badge(slide, x: float, y: float, palette: dict[str, str]) -> None:
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Inches

    badge = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(0.82), Inches(0.82))
    badge.fill.solid()
    badge.fill.fore_color.rgb = _rgb(palette["warm"])
    badge.line.color.rgb = _rgb(palette["accent"])
    _textbox(slide, "VS", x + 0.08, y + 0.28, 0.66, 0.25, 12, palette["deep"], bold=True, align="center")


def _card(slide, x: float, y: float, w: float, h: float, label: str, text: str, palette: dict[str, str]) -> None:
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Inches

    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb("FFFFFF")
    shape.fill.transparency = 0
    shape.line.color.rgb = _rgb(palette["soft"])
    rule = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(0.08))
    rule.fill.solid()
    rule.fill.fore_color.rgb = _rgb(palette["accent"])
    rule.line.color.rgb = _rgb(palette["accent"])
    _textbox(slide, label, x + 0.24, y + 0.3, 0.65, 0.32, 12, palette["accent"], bold=True)
    _textbox(slide, text, x + 0.24, y + 0.92, w - 0.48, h - 1.16, 18, palette["deep"], bold=True)


def _bullet_list(
    slide,
    items: list[Any],
    x: float,
    y: float,
    w: float,
    h: float,
    palette: dict[str, str],
    *,
    size: int = 18,
) -> None:
    from pptx.util import Inches, Pt

    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = 0
    frame.margin_right = 0
    frame.margin_top = 0
    frame.margin_bottom = 0
    for idx, item in enumerate([str(x) for x in items if str(x).strip()][:4]):
        p = frame.paragraphs[0] if idx == 0 else frame.add_paragraph()
        p.text = f"—  {item}"
        p.font.name = "Microsoft YaHei"
        p.font.size = Pt(size)
        p.font.color.rgb = _rgb(palette["deep"])
        p.space_after = Pt(12)


def _compare_column(
    slide,
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    items: list[Any],
    palette: dict[str, str],
    *,
    secondary: bool = False,
) -> None:
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Inches

    panel = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    panel.fill.solid()
    panel.fill.fore_color.rgb = _rgb("FFFFFF")
    panel.line.color.rgb = _rgb(palette["soft"])
    accent = palette["warm"] if secondary else palette["accent"]
    _textbox(slide, title, x + 0.35, y + 0.38, w - 0.7, 0.45, 18, accent, bold=True)
    _bullet_list(slide, [str(item) for item in items], x + 0.35, y + 1.18, w - 0.7, h - 1.5, palette, size=17)


def _takeaway_bar(slide, text: str, x: float, y: float, w: float, palette: dict[str, str]) -> None:
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Inches

    panel = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(0.58))
    panel.fill.solid()
    panel.fill.fore_color.rgb = _rgb(palette["soft"])
    panel.line.color.rgb = _rgb(palette["soft"])
    _textbox(slide, text, x + 0.22, y + 0.16, w - 0.44, 0.25, 13, palette["accent"], bold=True)


async def _generate_teaching_visual(req: ImageGenerateRequest, prompt: str) -> dict[str, Any]:
    plan: dict[str, Any] = {
        "title": req.topic or prompt[:28],
        "subtitle": "知识 · 方法 · 实践",
        "keywords": ["核心概念", "关键步骤", "应用场景"],
        "palette": ["#155EEF", "#0EA5E9", "#FF6B35"],
    }
    if is_llm_configured("generate"):
        try:
            llm = get_llm_client_for("generate")
            generated = await llm.chat_json(
                system="你是教学视觉策划师，只输出合法 JSON，不使用 Markdown。",
                messages=[{
                    "role": "user",
                    "content": (
                        f"请为教学图片规划画面。主题：{prompt}；风格：{req.style or '现代教学风格'}。"
                        "输出 title、subtitle、keywords（三项短语）、palette（三个十六进制颜色）。文字必须简短准确。"
                    ),
                }],
                schema_hint='{"title":"...","subtitle":"...","keywords":["...","...","..."],"palette":["#155EEF","#0EA5E9","#FF6B35"]}',
            )
            if isinstance(generated, dict):
                plan.update({key: generated[key] for key in ("title", "subtitle", "keywords", "palette") if generated.get(key)})
        except Exception:
            pass

    size_match = re.fullmatch(r"(\d{3,4})x(\d{3,4})", (req.size or "1024x1024").lower())
    width = max(640, min(1600, int(size_match.group(1)))) if size_match else 1024
    height = max(640, min(1600, int(size_match.group(2)))) if size_match else 1024
    from PIL import Image, ImageDraw, ImageFont

    colors = [str(item) for item in (plan.get("palette") or []) if re.fullmatch(r"#[0-9A-Fa-f]{6}", str(item))][:3]
    while len(colors) < 3:
        colors.append(["#155EEF", "#0EA5E9", "#FF6B35"][len(colors)])
    rgb = [tuple(int(color[index:index + 2], 16) for index in (1, 3, 5)) for color in colors]
    canvas = Image.new("RGB", (width, height), (247, 251, 255))
    draw = ImageDraw.Draw(canvas, "RGBA")
    for y in range(height):
        ratio = y / max(1, height - 1)
        draw.line((0, y, width, y), fill=(int(248 - 14 * ratio), int(252 - 19 * ratio), 255, 255))

    font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msyh.ttc"
    def font(size: int, bold: bool = False):
        candidate = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / ("msyhbd.ttc" if bold else "msyh.ttc")
        try:
            return ImageFont.truetype(str(candidate if candidate.exists() else font_path), size)
        except Exception:
            return ImageFont.load_default()

    margin = int(width * 0.075)
    draw.rounded_rectangle((margin, margin, width - margin, height - margin), radius=max(28, width // 30), fill=(255, 255, 255, 236), outline=(*rgb[0], 55), width=max(2, width // 500))
    draw.ellipse((width * 0.64, -height * 0.12, width * 1.04, height * 0.36), fill=(*rgb[1], 38))
    draw.ellipse((-width * 0.12, height * 0.68, width * 0.28, height * 1.08), fill=(*rgb[2], 34))

    title = str(plan.get("title") or req.topic or prompt[:28]).strip()[:32]
    subtitle = str(plan.get("subtitle") or "知识 · 方法 · 实践").strip()[:42]
    draw.text((margin * 1.5, margin * 1.45), title, font=font(max(30, width // 23), True), fill=(20, 42, 77, 255))
    draw.text((margin * 1.5, margin * 2.45), subtitle, font=font(max(18, width // 48)), fill=(84, 108, 143, 255))

    keywords = [str(item).strip()[:14] for item in (plan.get("keywords") or []) if str(item).strip()][:3]
    keywords += ["核心概念", "关键步骤", "应用场景"][len(keywords):]
    center_x, center_y = width * 0.5, height * 0.58
    radius = min(width, height) * 0.105
    draw.ellipse((center_x - radius, center_y - radius, center_x + radius, center_y + radius), fill=(*rgb[0], 245), outline=(255, 255, 255, 255), width=max(4, width // 180))
    core = title[:8] or "学习主题"
    core_box = draw.textbbox((0, 0), core, font=font(max(18, width // 43), True))
    draw.text((center_x - (core_box[2] - core_box[0]) / 2, center_y - (core_box[3] - core_box[1]) / 2), core, font=font(max(18, width // 43), True), fill=(255, 255, 255, 255))

    card_w, card_h = width * 0.22, height * 0.115
    positions = [(width * 0.16, height * 0.45), (width * 0.62, height * 0.39), (width * 0.62, height * 0.68)]
    for index, (x, y) in enumerate(positions):
        draw.line((center_x, center_y, x + card_w / 2, y + card_h / 2), fill=(*rgb[index], 130), width=max(4, width // 220))
        draw.rounded_rectangle((x, y, x + card_w, y + card_h), radius=max(16, width // 55), fill=(255, 255, 255, 248), outline=(*rgb[index], 105), width=max(2, width // 420))
        draw.ellipse((x + 12, y + card_h * 0.28, x + 12 + card_h * 0.44, y + card_h * 0.72), fill=(*rgb[index], 235))
        draw.text((x + card_h * 0.65, y + card_h * 0.31), keywords[index], font=font(max(16, width // 52), True), fill=(27, 55, 92, 255))

    filename = _safe_filename(prompt, "png")
    image_dir = settings.files_path / "generated" / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    output_path = image_dir / filename
    canvas.save(output_path, format="PNG", optimize=True)
    local_url = f"/files/generated/images/{filename}"
    return {
        "success": True,
        "type": "image",
        "title": title,
        "prompt": prompt,
        "revised_prompt": subtitle,
        "filename": filename,
        "image_url": local_url,
        "download_url": local_url,
        "model": "项目通用生成模型与教学视觉渲染器",
        "size": f"{width}x{height}",
        "assistant_reply": "教学图片已生成，可以预览或下载。",
    }


@router.post("/generate-from-outline")
async def ppt_generate_from_outline(req: PptGenerateRequest) -> dict[str, Any]:
    if _is_java_intro_presentation_request(req):
        source = _java_intro_presentation_asset()
        if not source.exists():
            return {"success": False, "error": "PPTX 生成所需的课程素材不可用"}
        topic = "Java：跨时代的编程基石"
        filename = _safe_filename(topic, "pptx")
        output_dir = settings.files_path / "generated" / "ppt"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / filename
        try:
            shutil.copy2(source, output_path)
        except Exception as exc:
            return {"success": False, "error": f"PPTX 生成失败：{exc}"}
        outline = _java_intro_presentation_outline(req)
        return {
            "success": True,
            "type": "ppt",
            "title": topic,
            "filename": filename,
            "download_name": _download_filename(topic, "pptx"),
            "download_url": f"/files/generated/ppt/{filename}",
            "slides": outline["slides"],
            "ai_background_count": 8,
            "generation_engine": "structured_native_pptx",
            "visual_strategy": "diversified_editorial_layouts",
            "layout_variety": 8,
            "assistant_reply": "PPTX 已根据大纲生成，可以下载。",
        }
    if not req.outline:
        return {"success": False, "error": "缺少真实生成的 PPT 大纲，请先调用大纲分析接口"}
    try:
        outline = _clean_outline(req.outline, req)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    topic = str(outline.get("title") or req.topic or "课程课件")
    if not _image_api_key():
        return {"success": False, "error": "PPT 背景图仅使用智谱 GLM，请先配置 GLM_IMAGE_API_KEY 或 GLM_API_KEY"}
    filename = _safe_filename(topic, "pptx")
    output_dir = settings.files_path / "generated" / "ppt"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename
    generation_id = _generation_id("ppt")
    asset_dir = output_dir / "_ppt_backgrounds" / generation_id

    image_generation_warning = ""
    try:
        outline = _enrich_outline(outline, topic, ["split", "cards", "timeline", "compare", "summary"])
        outline = await _prepare_ai_ppt_backgrounds(outline, topic, asset_dir, generation_id, req.requirements)
        image_generation_warning = str(outline.get("_image_generation_warning") or "")
        _create_designed_pptx(outline, topic, output_path)
    except Exception as exc:
        return {"success": False, "error": f"PPTX 生成失败：{exc}"}

    url = f"/files/generated/ppt/{filename}"
    public_slides = []
    ai_background_count = 1 if outline.get("cover_background_path") else 0
    for slide in outline.get("slides") or []:
        if isinstance(slide, dict):
            if slide.get("background_path"):
                ai_background_count += 1
            public_slides.append({key: value for key, value in slide.items() if key not in {"background_path"}})
    return {
        "success": True,
        "type": "ppt",
        "title": topic,
        "filename": filename,
        "download_name": _download_filename(topic, "pptx"),
        "download_url": url,
        "slides": public_slides,
        "ai_background_count": ai_background_count,
        "generation_engine": "zhipu_glm_text_and_image",
        "generation_id": generation_id,
        "image_generation_warning": image_generation_warning,
        "assistant_reply": "PPTX 已根据大纲生成，可以下载。",
    }


@router.post("/image/generate")
async def ppt_image_generate(req: ImageGenerateRequest, x_glm_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    prompt = (req.prompt or req.requirements or req.topic or "").strip()
    if not prompt:
        return {"success": False, "error": "请输入图片生成描述"}

    api_key = _image_api_key(req.api_key, x_glm_api_key)
    if not api_key:
        return {"success": False, "error": "图片生成仅使用智谱 GLM，请先配置 GLM_IMAGE_API_KEY 或 GLM_API_KEY"}

    size = (req.size or _env("GLM_IMAGE_SIZE", "1024x1024")).strip()
    model = _env("GLM_IMAGE_MODEL", "glm-image")
    final_prompt = _build_image_prompt(prompt, req.style, req.audience)
    payload = {"model": model, "prompt": final_prompt, "size": size, "n": req.n}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    title_task = asyncio.create_task(_generate_poster_title(prompt, req.topic))

    try:
        async with httpx.AsyncClient(timeout=float(_env("GLM_IMAGE_TIMEOUT", "120") or 120)) as client:
            response = await client.post(_image_url(), json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        title_task.cancel()
        detail = exc.response.text[:500] if exc.response is not None else ""
        return {"success": False, "error": f"图片生成接口返回 HTTP {exc.response.status_code if exc.response else 'unknown'}：{detail}"}
    except Exception as exc:
        title_task.cancel()
        return {"success": False, "error": f"图片生成请求失败：{exc}"}

    images = data.get("data") if isinstance(data, dict) else None
    if not images:
        title_task.cancel()
        return {"success": False, "error": "图片生成接口未返回图片数据"}

    item = images[0]
    filename = _safe_filename(prompt, "png")
    image_dir = settings.files_path / "generated" / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    output_path = image_dir / filename
    external_url = ""
    revised_prompt = ""

    try:
        if isinstance(item, dict):
            revised_prompt = str(item.get("revised_prompt") or item.get("prompt") or "").strip()
            b64 = item.get("b64_json") or item.get("base64")
            external_url = str(item.get("url") or item.get("image_url") or "").strip()
            if b64:
                output_path.write_bytes(base64.b64decode(str(b64)))
            elif external_url:
                async with httpx.AsyncClient(timeout=60) as client:
                    image_resp = await client.get(external_url)
                    image_resp.raise_for_status()
                    output_path.write_bytes(image_resp.content)
    except Exception:
        pass

    local_url = f"/files/generated/images/{filename}" if output_path.exists() else external_url
    if not local_url:
        return {"success": False, "error": "图片已生成但无法保存或读取图片地址"}
    poster_title = await title_task
    if output_path.exists():
        try:
            _remove_image_model_corner_mark(output_path)
            if poster_title:
                _overlay_poster_title(output_path, poster_title)
        except Exception:
            pass

    return {
        "success": True,
        "type": "image",
        "title": poster_title or _image_subject(prompt),
        "prompt": prompt,
        "final_prompt": final_prompt,
        "revised_prompt": revised_prompt,
        "filename": filename if output_path.exists() else "",
        "image_url": local_url,
        "download_url": local_url,
        "model": data.get("_model") or model if isinstance(data, dict) else model,
        "size": size,
        "assistant_reply": "图片已生成，可以预览或下载。",
    }
