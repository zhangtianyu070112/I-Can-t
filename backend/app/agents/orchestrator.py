from __future__ import annotations

import json
import logging
import re
import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator

from app.core.config import settings
from app.core.ids import new_id
from app.llm import get_glm_client, get_llm_client_for, is_glm_configured, is_llm_configured, parse_json_content
from app.repo import ensure_student, get_latest_profile_snapshot, insert_learning_event, insert_profile_snapshot, insert_resource_item, get_user_events, get_user_usages, list_resources
from app.services.exercise_bank import exercise_summary
from app.services.knowledge_hub import format_references, mastery_data, search_index


logger = logging.getLogger(__name__)


def _safe_text(s: str) -> str:
    return (s or "").strip()


def _bounded_score(value: Any, fallback: Any = 0) -> float:
    try:
        score = float(value if value not in (None, "") else fallback)
    except (TypeError, ValueError):
        score = 0.0
    return round(max(0.0, min(100.0, score)), 1)


def _mastery_level(value: Any) -> str:
    score = _bounded_score(value)
    if score >= 80:
        return "稳定掌握"
    if score >= 60:
        return "基本掌握"
    if score >= 40:
        return "持续提升"
    return "基础补强"


def _risk_level(value: Any) -> str:
    score = _bounded_score(value)
    if score >= 75:
        return "低风险"
    if score >= 55:
        return "中风险"
    return "高风险"


def _evidence_recommendations(*, accuracy: float, weak_points: list[str], disliked: int) -> list[str]:
    recommendations: list[str] = []
    if weak_points:
        recommendations.append(f"优先围绕“{weak_points[0]}”完成一次讲解、练习、复盘闭环")
    if accuracy < 60:
        recommendations.append("降低下一阶段题目跨度，先完成基础辨析题再进入综合应用")
    if disliked:
        recommendations.append("降低最近收到负反馈的资源类型权重，并切换为其他表达模态")
    if not recommendations:
        recommendations.append("继续积累答题、知识节点和资源反馈证据后再次评估")
    return recommendations[:3]


def _tutor_fallback_answer(references: list[dict[str, Any]], *, degraded: bool) -> dict[str, Any]:
    prefix = (
        "在线模型暂时不可用，已切换到本地知识库答疑框架。"
        if degraded
        else "未配置在线大模型，已使用本地知识库答疑框架。"
    )
    answer: dict[str, Any] = {
        "text": (
            f"{prefix}\n"
            "1) 复述问题并定位知识点\n"
            "2) 根据课程证据给出分步解释\n"
            "3) 给出一个最小例子\n"
            "4) 列出常见误区与自检方法\n"
            "5) 给出短视频分镜与画面提示"
        ),
        "diagram_hint": "可用 mermaid 或流程图展示关键步骤与变量变化",
        "video_storyboard": [
            {"scene": 1, "voice": "先说清问题是什么", "visual": "显示题目与关键词高亮"},
            {"scene": 2, "voice": "拆成三个小步骤", "visual": "逐步出现公式或伪代码"},
            {"scene": 3, "voice": "用一个例子跑一遍", "visual": "表格展示输入输出变化"},
        ],
        "references": references,
    }
    if degraded:
        answer["degraded_reason"] = "upstream_unavailable"
    return answer


def _default_path_steps(available: list[str]) -> list[dict[str, Any]]:
    base_docs = [item for item in ("lecture_doc", "mindmap") if item in available] or ["lecture_doc"]
    practice = [item for item in ("question_bank", "practice_case") if item in available] or ["question_bank"]
    review = [item for item in ("reading", "video_script") if item in available] or ["reading", "video_script"]
    return [
        {
            "order": 1,
            "objective": "学习状态诊断与薄弱点确认",
            "resources": ["question_bank"] if "question_bank" in available else practice,
            "assessment": "完成诊断题并标记错因，确认需要优先补强的 2 到 3 个知识点。",
        },
        {
            "order": 2,
            "objective": "补齐核心概念和知识结构",
            "resources": base_docs,
            "assessment": "能够用自己的话复述核心概念，并输出一张概念对照表或思维导图。",
        },
        {
            "order": 3,
            "objective": "围绕易错点进行强化练习",
            "resources": practice,
            "assessment": "同类题目正确率达到 80%，并能解释每个错误对应的知识点。",
        },
        {
            "order": 4,
            "objective": "通过实操案例完成知识迁移",
            "resources": ["practice_case"] if "practice_case" in available else practice,
            "assessment": "提交一个小型实操作品或案例分析，并说明用到了哪些课程知识。",
        },
        {
            "order": 5,
            "objective": "拓展阅读、多模态复盘与下一轮评估",
            "resources": review,
            "assessment": "输出复盘笔记和阶段评估，说明下一轮还需要系统推送哪些资源。",
        },
    ]


def _stabilize_path_plan(plan: Any, *, available: list[str]) -> dict[str, Any]:
    data = dict(plan) if isinstance(plan, dict) else {}
    raw_steps = data.get("steps") if isinstance(data.get("steps"), list) else []
    steps: list[dict[str, Any]] = []
    for index in range(len(raw_steps)):
        raw = raw_steps[index] if index < len(raw_steps) and isinstance(raw_steps[index], dict) else {}
        fallback = {
            "order": index + 1,
            "objective": "",
            "resources": [],
            "assessment": "",
        }
        resources = raw.get("resources") if isinstance(raw.get("resources"), list) else []
        steps.append(
            {
                **raw,
                "order": raw.get("order") or raw.get("step") or index + 1,
                "objective": raw.get("objective") or raw.get("title") or fallback["objective"],
                "resources": resources,
                "assessment": raw.get("assessment") or raw.get("checkpoint") or fallback["assessment"],
            }
        )

    strategy = data.get("strategy") if isinstance(data.get("strategy"), list) else []
    dynamic_rules = data.get("dynamic_rules") if isinstance(data.get("dynamic_rules"), list) else []
    data.update(
        {
            "title": data.get("title") or "个性化学习路径与资源推送方案",
            "steps": steps,
            "strategy": strategy,
            "dynamic_rules": dynamic_rules,
            "rationale": data.get("rationale") or "",
        }
    )
    return data


def _evidence_path_plan(
    *,
    goals: str,
    weak_points: list[str],
    weak_mastery_nodes: list[dict[str, Any]],
    tutor_questions: list[str],
    resources: list[dict[str, Any]],
    accuracy: float,
    attempts: int,
    liked_count: int,
    disliked_count: int,
) -> dict[str, Any]:
    """Create a variable path only from persisted learner evidence and the stated goal."""
    focus_items: list[str] = []
    for value in [
        *weak_points,
        *[str(item.get("name") or item.get("title") or "") for item in weak_mastery_nodes],
        *tutor_questions[-3:],
    ]:
        normalized = " ".join(str(value or "").split())[:80]
        if normalized and normalized not in focus_items:
            focus_items.append(normalized)

    resource_types = sorted({str(item.get("type") or "") for item in resources if item.get("type")})
    resource_titles = [str(item.get("title") or "") for item in resources if item.get("title")]
    steps: list[dict[str, Any]] = []

    for focus in focus_items[:3]:
        steps.append(
            {
                "order": len(steps) + 1,
                "objective": f"处理已识别薄弱点：{focus}",
                "resources": resource_types[:3],
                "assessment": f"围绕“{focus}”完成一次可记录的练习、复述或实操证据",
                "evidence_source": "profile_or_learning_history",
            }
        )

    if attempts and accuracy < 70:
        steps.append(
            {
                "order": len(steps) + 1,
                "objective": f"修复练习正确率偏低问题（当前 {accuracy:.1f}%）",
                "resources": [item for item in resource_types if item in {"lecture_doc", "mindmap", "question_bank"}],
                "assessment": "再次完成同知识点练习，并用新的作答记录验证变化",
                "evidence_source": "exercise_records",
            }
        )

    normalized_goal = " ".join(str(goals or "").split())[:160]
    if normalized_goal:
        steps.append(
            {
                "order": len(steps) + 1,
                "objective": f"达成用户目标：{normalized_goal}",
                "resources": resource_types,
                "assessment": "提交与目标对应的学习产物，并进入评估页面生成证据报告",
                "evidence_source": "user_goal",
            }
        )

    if resource_titles and not steps:
        steps.append(
            {
                "order": 1,
                "objective": "使用现有资源形成首轮学习证据",
                "resources": resource_types,
                "assessment": f"完成并反馈资源：{resource_titles[0]}",
                "evidence_source": "resource_history",
            }
        )

    if not steps:
        raise ValueError("尚无可用于路径分析的学习目标或行为证据，请先填写目标、更新画像或完成一次练习")

    strategy = [
        f"路径由 {len(focus_items)} 个薄弱信号、{attempts} 次作答和 {len(resources)} 份已有资源计算生成。",
    ]
    if resource_types:
        strategy.append("仅推荐当前学生已经生成的资源类型：" + "、".join(resource_types))
    if liked_count or disliked_count:
        strategy.append(f"资源反馈参与排序：有帮助 {liked_count} 次，负反馈 {disliked_count} 次。")

    dynamic_rules: list[str] = []
    if attempts:
        dynamic_rules.append(f"当前练习正确率为 {accuracy:.1f}%，后续作答会重新计算阶段优先级。")
    if weak_mastery_nodes:
        dynamic_rules.append(f"检测到 {len(weak_mastery_nodes)} 个低掌握知识节点，优先安排对应补强。")
    if disliked_count:
        dynamic_rules.append(f"检测到 {disliked_count} 次资源负反馈，同类资源在下一次规划中降权。")

    return {
        "title": f"围绕“{normalized_goal}”的证据驱动学习路径" if normalized_goal else "证据驱动学习路径",
        "steps": steps,
        "strategy": strategy,
        "dynamic_rules": dynamic_rules,
        "rationale": "；".join(strategy),
        "analysis_mode": "evidence_rules",
    }


def _guess_modality(text: str) -> str:
    t = text
    if any(k in t for k in ["视频", "动画", "讲解视频", "短视频"]):
        return "视频/动画优先"
    if any(k in t for k in ["图解", "流程图", "思维导图", "示意图"]):
        return "图解优先"
    if any(k in t for k in ["题", "刷题", "练习"]):
        return "练习驱动"
    return "文字优先"


def _guess_pace(text: str) -> str:
    if any(k in text for k in ["快", "速成", "赶进度"]):
        return "快节奏"
    if any(k in text for k in ["慢", "细讲", "从零"]):
        return "慢节奏"
    return "中等节奏"


def _guess_cognitive_style(text: str) -> str:
    if any(k in text for k in ["推导", "证明", "原理", "为什么"]):
        return "原理推导型"
    if any(k in text for k in ["例子", "类比", "直观"]):
        return "例子直观型"
    return "结构化步骤型"


def _extract_weak_points(text: str) -> list[str]:
    patterns = [
        r"(?:薄弱点是|薄弱点：|薄弱点:)([^，。；\n]{2,60})",
        r"(?:不懂|薄弱|不会|卡在|容易错在|容易错|总是错在)([^，。；\n]{2,40})",
        r"(?:^|[，。；：:\n])([^，。；：:\n]{2,40})容易出错",
        r"(?:^|[，。；：:\n])([^，。；：:\n]{2,40})(?:比较弱|不熟练)",
    ]
    raw: list[str] = []
    for p in patterns:
        raw.extend(re.findall(p, text))
    items: list[str] = []
    for r in raw:
        for part in re.split(r"[、,，和\s]+", r):
            part = _safe_text(part)
            if part.startswith("点是"):
                part = _safe_text(part[2:])
            if part.startswith("是"):
                part = _safe_text(part[1:])
            if not part:
                continue
            if len(part) > 30:
                continue
            items.append(part)
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out[:8]


def _extract_topic_keywords(text: str, weak_points: list[str]) -> list[str]:
    explicit = re.findall(r"(?:正在学习|正在学|课程是|课程[:：])([^，。；\n]{2,30})", text)
    terms = [_safe_text(item) for item in [*explicit, *weak_points]]
    return list(dict.fromkeys(item for item in terms if item))[:8]


def _extract_field(text: str, key: str) -> str:
    m = re.search(rf"{key}\s*[:：]\s*([^，。；\n]{{2,40}})", text)
    return _safe_text(m.group(1)) if m else ""


def _parse_json_maybe(text: str) -> dict[str, Any] | None:
    try:
        parsed = parse_json_content(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


_QUIZ_TYPE_LABELS = {
    "single_choice": "单选题",
    "multiple_choice": "多选题",
    "true_false": "判断题",
    "blank": "填空题",
    "short_answer": "简答题",
    "case_analysis": "案例分析题",
    "calculation": "计算题",
    "matching": "匹配题",
    "ordering": "排序题",
}


def _quiz_generation_config(requirement: dict[str, Any]) -> tuple[list[str], dict[str, int], int]:
    config = requirement.get("question_config") if isinstance(requirement.get("question_config"), dict) else {}
    requested = config.get("types") if isinstance(config.get("types"), list) else []
    allowed = [str(item) for item in requested if str(item) in _QUIZ_TYPE_LABELS]
    if not allowed:
        allowed = ["single_choice"]
    raw_counts = config.get("type_counts") if isinstance(config.get("type_counts"), dict) else {}
    counts = {
        item: max(0, min(20, int(raw_counts.get(item) or 0)))
        for item in allowed
    }
    counts = {key: value for key, value in counts.items() if value > 0}
    if not counts:
        total = max(1, min(50, int(config.get("count") or len(allowed))))
        counts = {item: max(1, total // len(allowed)) for item in allowed}
    total = max(1, min(50, int(config.get("count") or sum(counts.values()))))
    return list(counts), counts, total


def _constrain_quiz_payload(payload: dict[str, Any], requirement: dict[str, Any]) -> dict[str, Any]:
    allowed, counts, total = _quiz_generation_config(requirement)
    selected: list[dict[str, Any]] = []
    used = {item: 0 for item in allowed}
    raw_questions = payload.get("questions") if isinstance(payload.get("questions"), list) else []
    for item in raw_questions:
        if not isinstance(item, dict):
            continue
        question_type = str(item.get("type") or "").strip()
        if question_type not in used or used[question_type] >= counts[question_type]:
            continue
        selected.append(item)
        used[question_type] += 1
        if len(selected) >= total:
            break
    payload["questions"] = selected
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    payload["meta"] = {**meta, "requested_types": allowed, "requested_type_counts": counts}
    return payload


def _write_text(rel_path: str, content: str) -> str:
    p = settings.data_path / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return rel_path.replace("\\", "/")


def _load_resource_bodies(resources: list[dict[str, Any]], max_chars: int = 14000) -> list[dict[str, Any]]:
    loaded: list[dict[str, Any]] = []
    for resource in resources:
        content = ""
        content_uri = str(resource.get("content_uri") or "")
        if content_uri:
            path = settings.data_path / content_uri
            if path.exists() and path.is_file():
                content = path.read_text(encoding="utf-8", errors="replace")
        loaded.append(
            {
                "resource_id": resource.get("id"),
                "title": resource.get("title"),
                "type": resource.get("type"),
                "tags": resource.get("tags") or [],
                "content_chars": len(content),
                "content_truncated": len(content) > max_chars,
                "content": content[:max_chars],
            }
        )
    return loaded


def _deterministic_content_audit(
    resources: list[dict[str, Any]], references: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    reference_titles = [str(item.get("title") or "") for item in references]
    findings: list[dict[str, Any]] = []
    citation_pattern = re.compile(
        r"(?:https?://\S+|《[^》]{2,80}》|\b(?:19|20)\d{2}\b|第\s*\d+\s*(?:版|章|页)|"
        r"(?:GB|ISO|IEEE|RFC)\s*[-/:]?\s*[A-Z0-9.:-]+)",
        re.IGNORECASE,
    )
    for resource in resources:
        content = str(resource.get("content") or "")
        claims = sorted(set(citation_pattern.findall(content)))[:30]
        has_source_section = any(
            marker in content for marker in ("来源", "参考", "引用", "知识库参考", "待核验")
        )
        unsupported_markers = [
            claim
            for claim in claims
            if claim not in " ".join(reference_titles) and "待核验" not in content[max(0, content.find(claim) - 30) : content.find(claim) + len(claim) + 30]
        ]
        issues: list[str] = []
        if not content.strip():
            issues.append("资源正文为空，无法执行事实核验。")
        if claims and not has_source_section:
            issues.append("正文包含具体链接、书目、年份或标准编号，但没有来源/待核验说明。")
        if unsupported_markers:
            issues.append(f"发现 {len(unsupported_markers)} 个未与本地依据绑定的具体引用标记。")
        if resource.get("content_truncated"):
            issues.append("正文过长，本轮模型审查使用了截断文本，应对完整文件执行离线复核。")
        findings.append(
            {
                "resource_id": resource.get("resource_id"),
                "title": resource.get("title"),
                "claims": claims,
                "unsupported_markers": unsupported_markers,
                "has_source_section": has_source_section,
                "issues": issues,
            }
        )
    return findings


def _offline_audit_report(
    resources: list[dict[str, Any]], findings: list[dict[str, Any]]
) -> dict[str, Any]:
    audited: list[dict[str, Any]] = []
    highest = "pass"
    risk_score = 0
    finding_map = {item.get("resource_id"): item for item in findings}
    for resource in resources:
        finding = finding_map.get(resource.get("resource_id"), {})
        issues = list(finding.get("issues") or [])
        status = "warning" if issues else "pass"
        if not str(resource.get("content") or "").strip():
            status = "fail"
        if status == "fail":
            highest = "fail"
            risk_score = max(risk_score, 80)
        elif status == "warning" and highest != "fail":
            highest = "warning"
            risk_score = max(risk_score, 45)
        audited.append(
            {
                "resource_id": resource.get("resource_id"),
                "title": resource.get("title"),
                "status": status,
                "verified_claims": [],
                "unsupported_claims": finding.get("unsupported_markers") or [],
                "citation_issues": issues,
                "content_issues": ["未配置在线质检模型，当前仅执行确定性正文扫描。"],
                "rewrite_instructions": ["为具体事实补充本地知识库来源，无法核验时明确标注“待核验”。"] if issues else [],
            }
        )
    return {
        "overall_status": highest,
        "risk_score": risk_score,
        "summary": "已读取全部资源正文并完成确定性引用扫描；配置在线模型后可进一步进行语义事实核验。",
        "resources": audited,
        "global_actions": ["保留来源标记和待核验状态，禁止输出无法追溯的具体论文、版本、页码和链接。"],
    }


def _audit_markdown(audit: dict[str, Any], references: list[dict[str, Any]]) -> str:
    status_labels = {"pass": "通过", "warning": "需复核", "fail": "不通过"}
    status = str(audit.get("overall_status") or "warning").lower()
    lines = [
        "# 内容质检与防幻觉审查报告",
        "",
        "## 总体结论",
        f"- 审查状态：{status_labels.get(status, status)}",
        f"- 风险评分：{audit.get('risk_score', '--')}/100",
        f"- 结论摘要：{audit.get('summary') or '未提供'}",
        "- 审查范围：资源正文、事实主张、引用来源、题目答案、代码与结构完整性。",
        "",
        "## 分资源审查",
    ]
    for index, item in enumerate(audit.get("resources") or [], 1):
        item_status = str(item.get("status") or "warning").lower()
        lines.extend(
            [
                "",
                f"### {index}. {item.get('title') or item.get('resource_id') or '未命名资源'}",
                f"- 状态：{status_labels.get(item_status, item_status)}",
            ]
        )
        for label, key in (
            ("已核验主张", "verified_claims"),
            ("无依据主张", "unsupported_claims"),
            ("引用问题", "citation_issues"),
            ("内容问题", "content_issues"),
            ("修改要求", "rewrite_instructions"),
        ):
            values = item.get(key) or []
            if values:
                lines.append(f"- {label}：")
                lines.extend(f"  - {value}" for value in values)
    actions = audit.get("global_actions") or []
    if actions:
        lines.extend(["", "## 全局修正动作"])
        lines.extend(f"- {action}" for action in actions)
    lines.extend(["", "## 本轮知识库依据"])
    if references:
        for item in references:
            lines.append(f"- {item.get('title')}（匹配度 {item.get('score')}）")
    else:
        lines.append("- 未检索到高相关本地依据，所有具体外部事实均需标注“待核验”。")
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class AgentSpec:
    key: str
    title: str
    resource_type: str
    ext: str


AGENTS: list[AgentSpec] = [
    AgentSpec(key="lecture", title="专业课程讲解文档", resource_type="lecture_doc", ext="md"),
    AgentSpec(key="mindmap", title="知识点思维导图", resource_type="mindmap", ext="md"),
    AgentSpec(key="quiz", title="个性化题库", resource_type="question_bank", ext="json"),
    AgentSpec(key="reading", title="拓展阅读材料", resource_type="reading", ext="md"),
    AgentSpec(key="practice", title="代码/实操案例", resource_type="practice_case", ext="md"),
    AgentSpec(key="video", title="多模态视频/动画脚本", resource_type="video_script", ext="md"),
]


def _requested_agents(requirement: dict[str, Any]) -> list[AgentSpec]:
    raw_types = requirement.get("resource_types") or []
    requested = {str(item).strip() for item in raw_types if str(item).strip()} if isinstance(raw_types, list) else set()
    if not requested:
        single = str(requirement.get("resource_type") or "").strip()
        requested = {single} if single else set()
    if not requested:
        raise ValueError("至少选择一种资源类型，后端不会再默认执行全部生成智能体")
    selected = [spec for spec in AGENTS if spec.resource_type in requested]
    unknown = requested - {spec.resource_type for spec in selected}
    if unknown:
        raise ValueError("不支持的资源类型：" + "、".join(sorted(unknown)))
    return selected


class Orchestrator:
    async def profile_chat(
        self,
        *,
        student_id: str,
        messages: list[dict[str, str]],
        major: str | None,
        goals: str | None,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        ensure_student(student_id=student_id, major=major, goals=goals)
        prev = get_latest_profile_snapshot(student_id)
        user_text = "\n".join([m["content"] for m in messages if m["role"] == "user"])[-2000:]
        
        # 引入本地历史数据：资源反馈与答疑记录（潜在问题）
        usages = get_user_usages(student_id)
        events = get_user_events(student_id)
        negative_feedbacks = [u for u in usages if u.get("action") == "dislike"]
        tutor_questions = [e.get("payload", {}).get("question") for e in events if e.get("event_type") == "tutor"]
        
        history_context = ""
        if negative_feedbacks or tutor_questions:
            history_context = "【系统注入：用户历史潜在问题】\n"
            if negative_feedbacks:
                history_context += f"- 近期对 {len(negative_feedbacks)} 个资源表示不喜欢（可能内容不匹配或过难）。\n"
            if tutor_questions:
                history_context += f"- 近期答疑记录（反映薄弱点）：{'; '.join(tutor_questions[-3:])}\n"

        base_profile = {
            "knowledge_base_level": prev.get("knowledge_base_level", "") if prev else "",
            "cognitive_style": prev.get("cognitive_style", "") if prev else "",
            "mistake_patterns": prev.get("mistake_patterns", "") if prev else "",
            "modality_preference": prev.get("modality_preference", "") if prev else "",
            "pace_preference": prev.get("pace_preference", "") if prev else "",
            "motivation_style": prev.get("motivation_style", "") if prev else "",
        }

        if is_llm_configured("profile"):
            llm = get_llm_client_for("profile")
            schema_hint = (
                '{"knowledge_base_level": "...", "cognitive_style": "...", "mistake_patterns": "...", '
                '"modality_preference": "...", "pace_preference": "...", "motivation_style": "...", '
                '"rationale": "...", "evidence": {"weak_points": ["..."], "keywords": ["..."]}}'
            )
            
            # 将历史潜在问题注入到对话最后一条中，让模型参考
            if history_context:
                messages = list(messages)
                last_msg = messages[-1]
                messages[-1] = {"role": last_msg["role"], "content": last_msg["content"] + "\n\n" + history_context}
                
            data = await llm.chat_json(messages=messages, schema_hint=schema_hint, on_chunk=on_chunk)
            profile = {**base_profile, **(data or {})}
            rationale = str(profile.pop("rationale", "") or "")
            evidence = profile.pop("evidence", {}) if isinstance(profile.get("evidence", {}), dict) else {}
        else:
            weak_points = _extract_weak_points(user_text)
            if tutor_questions:
                weak_points.extend(tutor_questions[-2:])
            profile = {
                **base_profile,
                "knowledge_base_level": base_profile["knowledge_base_level"] or "待评估",
                "cognitive_style": base_profile["cognitive_style"] or _guess_cognitive_style(user_text),
                "mistake_patterns": "; ".join(weak_points) if weak_points else (base_profile["mistake_patterns"] or "待采集"),
                "modality_preference": base_profile["modality_preference"] or _guess_modality(user_text),
                "pace_preference": base_profile["pace_preference"] or _guess_pace(user_text),
                "motivation_style": base_profile["motivation_style"] or "目标驱动",
            }
            rationale = "已基于对话内容及本地历史潜在问题进行启发式画像抽取；配置在线大模型后可获得更精准的维度识别与依据。"
            evidence = {"weak_points": weak_points, "keywords": _extract_topic_keywords(user_text, weak_points)}

        snapshot = insert_profile_snapshot(student_id=student_id, profile=profile, evidence=evidence)
        insert_learning_event(student_id, "profile_update", {"snapshot_id": snapshot["id"]})

        delta: dict[str, Any] = {}
        if prev:
            for k in [
                "knowledge_base_level",
                "cognitive_style",
                "mistake_patterns",
                "modality_preference",
                "pace_preference",
                "motivation_style",
            ]:
                if prev.get(k) != snapshot.get(k):
                    delta[k] = {"from": prev.get(k), "to": snapshot.get(k)}

        return {"snapshot": snapshot, "delta": delta, "rationale": rationale}

    async def clarify(
        self,
        *,
        student_id: str,
        messages: list[dict[str, str]],
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        user_text = "\n".join([m["content"] for m in messages if m["role"] == "user"])[-2000:]
        weak_points = _extract_weak_points(user_text)

        if is_llm_configured("clarify"):
            llm = get_llm_client_for("clarify")
            schema_hint = (
                '{"course": "...", "chapter": "...", "goals": "...", "weak_points": ["..."], '
                '"preferred_resources": ["lecture_doc","mindmap","question_bank","reading","practice_case","video_script"], '
                '"constraints": {"time_budget": "...", "difficulty": "..."}}'
            )
            data = await llm.chat_json(messages=messages, schema_hint=schema_hint, on_chunk=on_chunk)
            requirement = data or {}
            if not isinstance(requirement.get("weak_points"), list):
                requirement["weak_points"] = weak_points
        else:
            course = _extract_field(user_text, "课程")
            chapter = _extract_field(user_text, "章节")
            goals = _extract_field(user_text, "目标")
            requirement = {
                "course": course,
                "chapter": chapter,
                "goals": goals,
                "weak_points": weak_points,
                "preferred_resources": [a.resource_type for a in AGENTS],
                "constraints": {"time_budget": "", "difficulty": ""},
                "note": "未配置在线大模型：当前为启发式需求单，可在设置页填入模型信息后重新澄清。",
            }

        insert_learning_event(student_id, "clarify", {"weak_points": weak_points})
        return {"requirement": requirement}

    async def generate(
        self,
        *,
        student_id: str,
        requirement: dict[str, Any],
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> list[dict[str, Any]]:
        resources: list[dict[str, Any]] = []
        selected_agents = _requested_agents(requirement)
        generated_contents = await asyncio.gather(*[
            self._generate_one(spec=spec, requirement=requirement, student_id=student_id, on_chunk=on_chunk)
            for spec in selected_agents
        ])
        for spec, content in zip(selected_agents, generated_contents):
            file_id = new_id()
            rel_path = f"files/{student_id}/{file_id}.{spec.ext}"
            content_uri = _write_text(rel_path, content)
            meta = {"agent": spec.key, "requirement": requirement}
            item = insert_resource_item(
                student_id=student_id,
                type=spec.resource_type,
                title=spec.title,
                tags=(requirement.get("weak_points") or [])[:5],
                content_uri=content_uri,
                meta=meta,
            )
            resources.append(item)

        constraints = requirement.get("constraints") if isinstance(requirement.get("constraints"), dict) else {}
        qa_item = None if constraints.get("skip_quality_check") else await self._run_quality_check(
            resources=resources,
            requirement=requirement,
            student_id=student_id,
            on_chunk=on_chunk,
        )
        if qa_item:
            resources.append(qa_item)

        insert_learning_event(student_id, "generate", {"count": len(resources)})
        return resources

    async def stream_generate(
        self, *, student_id: str, requirement: dict[str, Any]
    ) -> AsyncIterator[dict[str, Any]]:
        selected_agents = _requested_agents(requirement)
        constraints = requirement.get("constraints") if isinstance(requirement.get("constraints"), dict) else {}
        run_quality_check = not constraints.get("skip_quality_check")
        agent_keys = [a.key for a in selected_agents] + (["quality_check"] if run_quality_check else [])
        yield {"type": "start", "ts": datetime.utcnow().isoformat(), "agents": agent_keys}
        resources: list[dict[str, Any]] = []
        for idx, spec in enumerate(selected_agents):
            yield {"type": "agent_start", "agent": spec.key, "title": spec.title, "index": idx}
            queue: asyncio.Queue[str] = asyncio.Queue()

            async def on_chunk(text: str) -> None:
                await queue.put(text)

            task = asyncio.create_task(
                self._generate_one(
                    spec=spec,
                    requirement=requirement,
                    student_id=student_id,
                    on_chunk=on_chunk,
                )
            )
            while not task.done() or not queue.empty():
                try:
                    text = await asyncio.wait_for(queue.get(), timeout=0.08)
                    yield {"type": "agent_chunk", "agent": spec.key, "text": text}
                except asyncio.TimeoutError:
                    continue
            content = await task
            file_id = new_id()
            rel_path = f"files/{student_id}/{file_id}.{spec.ext}"
            content_uri = _write_text(rel_path, content)
            meta = {"agent": spec.key, "requirement": requirement}
            item = insert_resource_item(
                student_id=student_id,
                type=spec.resource_type,
                title=spec.title,
                tags=(requirement.get("weak_points") or [])[:5],
                content_uri=content_uri,
                meta=meta,
            )
            resources.append(item)
            yield {"type": "agent_done", "agent": spec.key, "resource": item}

        if not run_quality_check:
            insert_learning_event(student_id, "generate", {"count": len(resources)})
            yield {"type": "done", "ts": datetime.utcnow().isoformat()}
            return

        yield {"type": "agent_start", "agent": "quality_check", "title": "内容质检与防幻觉审查", "index": len(selected_agents)}
        qa_queue: asyncio.Queue[str] = asyncio.Queue()

        async def on_qa_chunk(text: str) -> None:
            await qa_queue.put(text)

        qa_task = asyncio.create_task(
            self._run_quality_check(
                resources=resources,
                requirement=requirement,
                student_id=student_id,
                on_chunk=on_qa_chunk,
            )
        )
        while not qa_task.done() or not qa_queue.empty():
            try:
                text = await asyncio.wait_for(qa_queue.get(), timeout=0.08)
                yield {"type": "agent_chunk", "agent": "quality_check", "text": text}
            except asyncio.TimeoutError:
                continue
        qa_item = await qa_task
        if qa_item:
            yield {"type": "agent_done", "agent": "quality_check", "resource": qa_item}

        insert_learning_event(student_id, "generate", {"count": len(resources) + (1 if qa_item else 0)})
        yield {"type": "done", "ts": datetime.utcnow().isoformat()}

    async def plan_path(
        self,
        *,
        student_id: str,
        goals: str | None,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        profile = get_latest_profile_snapshot(student_id) or {}
        weak_points = (profile.get("evidence") or {}).get("weak_points", [])
        resources = list_resources(student_id)
        usages = get_user_usages(student_id)
        events = get_user_events(student_id)
        tutor_questions = [e.get("payload", {}).get("question", "") for e in events if e.get("event_type") == "tutor"]
        disliked = [u for u in usages if u.get("action") == "dislike"]
        liked = [u for u in usages if u.get("action") == "like"]
        knowledge_mastery = mastery_data(student_id)
        exercise = exercise_summary(student_id)
        weak_mastery_nodes = [
            n for n in knowledge_mastery.get("nodes", [])
            if int(n.get("evidence_count") or 0) > 0 and float(n.get("current_mastery", 0)) < 60
        ][:4]

        resource_types = sorted({r.get("type", "") for r in resources if r.get("type")})
        available = resource_types
        recent_problem_text = "；".join([str(x) for x in weak_points + tutor_questions[-3:] if x])

        if is_llm_configured("plan"):
            llm = get_llm_client_for("plan")
            prompt = (
                "请为学生规划学习路径，输出 JSON："
                '{"title":"...","steps":[{"order":1,"objective":"...","resources":["lecture_doc"],"assessment":"..."}],'
                '"strategy":["..."],"dynamic_rules":["..."],"rationale":"..."}'
            )
            data = await llm.chat_json(
                messages=[
                    {"role": "user", "content": f"学生画像：{json.dumps(profile, ensure_ascii=False)}"},
                    {"role": "user", "content": f"学习目标：{goals or ''}"},
                    {"role": "user", "content": f"已生成资源类型：{json.dumps(resource_types, ensure_ascii=False)}"},
                    {"role": "user", "content": f"近期薄弱点与答疑问题：{recent_problem_text}"},
                    {"role": "user", "content": f"知识图谱掌握度：{json.dumps(knowledge_mastery.get('summary', {}), ensure_ascii=False)}；低掌握节点：{json.dumps(weak_mastery_nodes, ensure_ascii=False)}"},
                    {"role": "user", "content": f"资源反馈：喜欢 {len(liked)} 条，不喜欢 {len(disliked)} 条"},
                ],
                schema_hint=prompt,
                on_chunk=on_chunk,
            )
            plan = data or {}
            if not isinstance(plan.get("steps"), list) or not plan.get("steps"):
                raise RuntimeError("路径规划模型没有返回可执行步骤，本次没有生成固定路径")
            plan["analysis_mode"] = "llm"
            plan["evidence_summary"] = {
                "profile_snapshot_id": profile.get("id"),
                "weak_point_count": len(weak_points),
                "weak_mastery_node_count": len(weak_mastery_nodes),
                "exercise_attempts": int(exercise.get("total") or 0),
                "resource_count": len(resources),
                "feedback_count": len(usages),
                "goal": str(goals or "").strip(),
            }
        else:
            base_docs = [r for r in ["lecture_doc", "mindmap"] if r in available] or ["lecture_doc"]
            practice_resources = [r for r in ["question_bank", "practice_case"] if r in available] or ["question_bank"]
            review_resources = [r for r in ["reading", "video_script"] if r in available] or ["reading", "video_script"]
            weak_desc = "、".join(weak_points) if weak_points else "待进一步诊断"
            weak_mastery_desc = "、".join([n.get("name", "") for n in weak_mastery_nodes if n.get("name")]) or "暂无低掌握图谱节点"
            plan = {
                "title": "个性化学习路径与资源推送方案",
                "strategy": [
                    "先诊断薄弱点，再补齐概念框架，随后进入练习和实操迁移。",
                    "优先使用学生已经生成或最近使用过的资源，避免学习材料分散。",
                    "根据答疑问题、资源反馈和练习结果动态调整下一阶段资源权重。",
                    f"结合知识图谱掌握度，优先处理低掌握节点：{weak_mastery_desc}。",
                ],
                "steps": [
                    {
                        "order": 1,
                        "objective": "学习状态诊断与薄弱点确认",
                        "resources": ["question_bank"] if "question_bank" in available else practice_resources,
                        "assessment": "完成诊断题并标记错因，确认需要优先补强的 2 到 3 个知识点。",
                    },
                    {
                        "order": 2,
                        "objective": "补齐核心概念和知识结构",
                        "resources": base_docs,
                        "assessment": "能够用自己的话复述核心概念，并输出一张概念对照表或思维导图。",
                    },
                    {
                        "order": 3,
                        "objective": "围绕易错点进行强化练习",
                        "resources": practice_resources,
                        "assessment": "同类题目正确率达到 80%，并能解释每个错误对应的知识点。",
                    },
                    {
                        "order": 4,
                        "objective": "通过实操案例完成知识迁移",
                        "resources": ["practice_case"] if "practice_case" in available else practice_resources,
                        "assessment": "提交一个小型实操作品或案例分析，并说明用到了哪些课程知识。",
                    },
                    {
                        "order": 5,
                        "objective": "拓展阅读与多模态复盘",
                        "resources": review_resources,
                        "assessment": "输出复盘笔记，说明下一轮学习还需要系统推送哪些资源。",
                    },
                ],
                "dynamic_rules": [
                    "若诊断题正确率低于 60%，回到第 2 步并提高讲解文档、思维导图、视频脚本的推荐权重。",
                    "若学生对某类资源连续点踩，降低该类型资源排序，并改推同知识点的其他模态资源。",
                    "若答疑中反复出现同一知识点，将该知识点加入下一轮路径的第 1 优先级。",
                    "若连续两次阶段任务达标，进入进阶阅读或实操案例，减少基础讲解资源推送。",
                ],
                "rationale": f"当前启发式规划；已识别弱点：{weak_desc}；知识图谱低掌握节点：{weak_mastery_desc}；已生成资源类型：{', '.join(resource_types) if resource_types else '暂无，将使用默认资源类型'}。",
            }

        if not is_llm_configured("plan"):
            plan = _evidence_path_plan(
                goals=str(goals or ""),
                weak_points=[str(item) for item in weak_points],
                weak_mastery_nodes=weak_mastery_nodes,
                tutor_questions=[str(item) for item in tutor_questions if item],
                resources=resources,
                accuracy=float(exercise.get("accuracy") or 0),
                attempts=int(exercise.get("total") or 0),
                liked_count=len(liked),
                disliked_count=len(disliked),
            )
        plan = _stabilize_path_plan(plan, available=available)
        insert_learning_event(
            student_id,
            "path_plan",
            {"title": plan.get("title"), "goals": goals, "path": plan},
        )
        return {"plan": plan}

    async def tutor_ask(
        self,
        *,
        student_id: str,
        question: str,
        context: dict[str, Any],
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        profile = get_latest_profile_snapshot(student_id) or {}
        references = search_index(student_id=student_id, query=question, limit=3)
        reference_text = format_references(references)
        if is_llm_configured("tutor"):
            llm = get_llm_client_for("tutor")
            system = "你是耐心的大学课程助教，优先基于知识库参考回答；参考不足时必须标注待核验。输出结构化解答，包含文字步骤、图解建议、以及短视频讲解分镜。"
            try:
                request = llm.chat_text(
                    system=system,
                    messages=[
                        {"role": "user", "content": f"学生画像：{json.dumps(profile, ensure_ascii=False)}"},
                        {"role": "user", "content": reference_text or "知识库未命中高相关片段。"},
                        {"role": "user", "content": f"问题：{question}"},
                        {"role": "user", "content": f"上下文：{json.dumps(context, ensure_ascii=False)}"},
                    ],
                    temperature=0.4,
                    on_chunk=on_chunk,
                )
                if on_chunk:
                    text = await request
                else:
                    response_budget = max(5.0, min(float(settings.llm_timeout_sec), 60.0))
                    text = await asyncio.wait_for(request, timeout=response_budget)
                answer = {"text": text}
                parsed = _parse_json_maybe(text)
                if parsed:
                    answer = parsed
            except Exception as exc:
                logger.warning("Tutor LLM unavailable; refusing synthetic fallback (%s)", type(exc).__name__)
                raise RuntimeError("智能辅导模型暂时不可用，本次没有生成回答，也没有写入伪造分析结果") from exc
        else:
            raise RuntimeError("智能辅导模型尚未配置，本次没有生成回答，也没有写入伪造分析结果")

        if isinstance(answer, dict):
            answer.setdefault("references", references)
        insert_learning_event(student_id, "tutor", {"question": question[:120]})
        return {"answer": answer}

    async def evaluate(
        self,
        *,
        student_id: str,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        profile = get_latest_profile_snapshot(student_id) or {}
        
        # 收集历史潜在问题与交互数据
        usages = get_user_usages(student_id)
        events = get_user_events(student_id)
        knowledge_mastery = mastery_data(student_id)
        exercise = exercise_summary(student_id)
        
        history_summary = {
            "total_resources_used": len(usages),
            "liked_resources": len([u for u in usages if u.get("action") == "like"]),
            "disliked_resources": len([u for u in usages if u.get("action") == "dislike"]),
            "tutor_questions_asked": len([e for e in events if e.get("event_type") == "tutor"]),
            "exercise_total": exercise.get("total", 0),
            "exercise_accuracy": exercise.get("accuracy", 0),
            "exercise_weak_tags": exercise.get("weak_tags", []),
            "recent_tutor_topics": [e.get("payload", {}).get("question") for e in events if e.get("event_type") == "tutor"][-5:]
        }
        
        if is_llm_configured("evaluate"):
            llm = get_llm_client_for("evaluate")
            schema_hint = (
                '{"summary":"...",'
                '"dimensions":{"knowledge_mastery":0,"stability":0,"transfer":0,"resource_efficiency":0},'
                '"weak_points":["..."],'
                '"recommendations":["..."],'
                '"next_actions":["..."]}'
            )
            data = await llm.chat_json(
                messages=[
                    {"role": "user", "content": f"学生画像快照：{json.dumps(profile, ensure_ascii=False)}"},
                    {"role": "user", "content": f"近期行为与潜在问题数据：{json.dumps(history_summary, ensure_ascii=False)}"},
                    {"role": "user", "content": f"知识图谱掌握度与复习预警：{json.dumps(knowledge_mastery, ensure_ascii=False)}"},
                    {"role": "user", "content": f"练习闭环统计与错题：{json.dumps(exercise, ensure_ascii=False)}"},
                    {
                        "role": "user",
                        "content": "请基于画像和本地行为数据输出学习效果评估报告（重点分析潜在问题并给出闭环优化建议）。",
                    },
                ],
                schema_hint=schema_hint,
                on_chunk=on_chunk,
            )
            report = data or {}
            report["profile_snapshot_id"] = profile.get("id")
            report["knowledge_mastery_summary"] = knowledge_mastery.get("summary", {})
            report["exercise_summary"] = exercise
            report["analysis_mode"] = "llm"
        else:
            report = {"analysis_mode": "evidence_rules"}

        dimensions = report.get("dimensions") if isinstance(report.get("dimensions"), dict) else {}
        normalized_dimensions = {
            "knowledge_mastery": _bounded_score(
                dimensions.get("knowledge_mastery"),
                knowledge_mastery.get("summary", {}).get("average_mastery", 0),
            ),
            "stability": _bounded_score(dimensions.get("stability"), exercise.get("accuracy", 0)),
            "transfer": _bounded_score(dimensions.get("transfer"), min(100, len(events) * 4)),
            "resource_efficiency": _bounded_score(
                dimensions.get("resource_efficiency"),
                round(len(usages) * 100 / max(1, len(list_resources(student_id))), 1),
            ),
        }
        overall_score = round(
            normalized_dimensions["knowledge_mastery"] * 0.35
            + normalized_dimensions["stability"] * 0.25
            + normalized_dimensions["transfer"] * 0.2
            + normalized_dimensions["resource_efficiency"] * 0.2,
            1,
        )
        weak_points = [str(item.get("tag")) for item in exercise.get("weak_tags", []) if item.get("tag")]
        weak_points.extend(
            str(item.get("name"))
            for item in knowledge_mastery.get("nodes", [])
            if float(item.get("current_mastery", 0)) < 60 and item.get("name")
        )
        weak_points.extend(str(item) for item in (profile.get("evidence") or {}).get("weak_points", []) if item)
        weak_points = list(dict.fromkeys(weak_points))[:8]
        if report.get("analysis_mode") == "evidence_rules":
            evidence_count = history_summary["exercise_total"] + history_summary["total_resources_used"] + len(events)
            report.update(
                {
                    "summary": (
                        f"本次评估读取 {evidence_count} 条本地行为证据、"
                        f"{history_summary['exercise_total']} 次练习和 {len(knowledge_mastery.get('nodes', []))} 个知识节点；"
                        f"练习正确率 {history_summary['exercise_accuracy']}%，综合得分 {overall_score}。"
                    ),
                    "findings": [
                        f"练习正确率为 {history_summary['exercise_accuracy']}%",
                        f"资源正反馈 {history_summary['liked_resources']} 次、负反馈 {history_summary['disliked_resources']} 次",
                        f"最近累计提问 {history_summary['tutor_questions_asked']} 次",
                    ],
                    "weak_points": weak_points,
                    "recommendations": _evidence_recommendations(
                        accuracy=float(history_summary["exercise_accuracy"] or 0),
                        weak_points=weak_points,
                        disliked=int(history_summary["disliked_resources"]),
                    ),
                    "profile_snapshot_id": profile.get("id"),
                    "knowledge_mastery_summary": knowledge_mastery.get("summary", {}),
                    "exercise_summary": exercise,
                }
            )
        report.update(
            {
                "dimensions": normalized_dimensions,
                "overall_score": overall_score,
                "mastery_level": _mastery_level(knowledge_mastery.get("summary", {}).get("average_mastery", 0)),
                "risk_level": _risk_level(overall_score),
                "evidence_summary": history_summary,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        insert_learning_event(student_id, "evaluate", {"report": report})
        return {"report": report}

    async def _run_quality_check(
        self,
        resources: list[dict[str, Any]],
        requirement: dict[str, Any],
        student_id: str,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> dict[str, Any] | None:
        audited_resources = _load_resource_bodies(resources)
        reference_query = " ".join(
            [
                str(requirement.get("course", "")),
                str(requirement.get("chapter", "")),
                " ".join(map(str, requirement.get("weak_points") or [])),
            ]
        )
        references = search_index(student_id=student_id, query=reference_query, limit=6)
        reference_text = format_references(references)
        deterministic_findings = _deterministic_content_audit(audited_resources, references)

        if is_llm_configured("generate"):
            llm = get_llm_client_for("generate")
            system = (
                "你是正文级内容质检与防幻觉智能体。必须阅读每份资源正文，逐项核验事实主张、引用、链接、"
                "标准版本、论文书目信息、题目答案和代码可执行性。不得只根据标题判断。"
                "输出严格 JSON，不要输出 Markdown 代码围栏。"
            )
            schema_hint = (
                '{"overall_status":"pass|warning|fail","risk_score":0,'
                '"summary":"...","resources":[{"resource_id":"...","title":"...",'
                '"status":"pass|warning|fail","verified_claims":["..."],'
                '"unsupported_claims":["..."],"citation_issues":["..."],'
                '"content_issues":["..."],"rewrite_instructions":["..."]}],'
                '"global_actions":["..."]}'
            )
            prompt = f"""
请对本次多智能体生成资源执行正文级审查。

需求单：
{json.dumps(requirement, ensure_ascii=False, indent=2)}

本地知识库检索依据：
{reference_text or "未检索到可靠依据；所有具体外部事实、版本、论文、链接均应标为待核验。"}

程序预检结果：
{json.dumps(deterministic_findings, ensure_ascii=False, indent=2)}

待审查资源正文：
{json.dumps(audited_resources, ensure_ascii=False, indent=2)}

审查要求：
1. 对每份资源给出独立结论，不得遗漏。
2. 无法由知识库依据支持的具体事实必须列入 unsupported_claims 或 citation_issues。
3. 发现错误答案、矛盾定义、虚假链接、具体版本/页码无依据时，status=fail。
4. 仅缺少来源但内容可能正确时，status=warning，并给出可执行 rewrite_instructions。
5. risk_score 范围 0-100，风险越高分数越高。
"""
            audit = await llm.chat_json(
                messages=[{"role": "user", "content": prompt}],
                schema_hint=schema_hint,
                on_chunk=on_chunk,
            )
        else:
            audit = _offline_audit_report(audited_resources, deterministic_findings)

        content = _audit_markdown(audit, references)

        file_id = new_id()
        rel_path = f"files/{student_id}/{file_id}.md"
        content_uri = _write_text(rel_path, content)
        meta = {
            "agent": "quality_check",
            "requirement": requirement,
            "audit": audit,
            "reference_count": len(references),
            "body_level": True,
        }
        item = insert_resource_item(
            student_id=student_id,
            type="quality_check",
            title="内容质检与防幻觉审查报告",
            tags=["质检", "防幻觉"],
            content_uri=content_uri,
            meta=meta,
        )
        return item

    async def _generate_one(
        self,
        *,
        spec: AgentSpec,
        requirement: dict[str, Any],
        student_id: str,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        profile = get_latest_profile_snapshot(student_id) or {}
        reference_query = " ".join(
            [
                str(requirement.get("course", "")),
                str(requirement.get("chapter", "")),
                " ".join(map(str, requirement.get("weak_points") or [])),
                spec.title,
            ]
        )
        reference_text = format_references(search_index(student_id=student_id, query=reference_query, limit=4))
        
        constraints = requirement.get("constraints") if isinstance(requirement.get("constraints"), dict) else {}
        use_glm = spec.key == "quiz" and constraints.get("source") in {
            "exercise_custom_bank",
            "multimodal_chat_quiz",
            "path_stage_quiz",
        }
        model_configured = is_glm_configured() if use_glm else is_llm_configured("generate")
        if model_configured:
            llm = get_glm_client() if use_glm else get_llm_client_for("generate")
            
            # 引入软件杯优质Prompt模板
            if spec.key == "lecture":
                system = (
                    "你是高校课程资源生成智能体，负责生成严谨、结构完整、适合学生自学的中文 Markdown 课程讲解文档。"
                    "不要编造不存在的教材页码、论文和链接；不确定的事实必须标注“待核验”。"
                )
                user_content = f"""请基于以下信息生成一份“专业课程讲解文档”。
学生画像：{json.dumps(profile, ensure_ascii=False)}
需求单：{json.dumps(requirement, ensure_ascii=False)}
课程知识库参考：
{reference_text or "未检索到高相关参考，请仅基于确定知识生成，并标注待核验内容。"}

输出要求：
1. 只输出 Markdown，不要输出解释性前言。
2. 必须包含：文档概览、学习目标、先修知识、核心概念、关键公式/流程/模型、标准学习流程、针对知识短板的讲解、专业案例、可模仿模板、常见误区、课堂练习、自检清单、课后复盘任务。
3. 核心概念至少拆成 3 到 6 个小节，每节包含“定义/作用/例子/易错点/自测题”。
4. 内容要针对学生画像，不要泛泛而谈；若学生基础弱，先给直观类比，再给正式定义。"""
            
            elif spec.key == "reading":
                system = (
                    "你是高校课程拓展阅读规划智能体，负责生成分层、可执行、带产出要求的中文 Markdown 阅读材料。"
                    "不要编造真实链接、论文页码和具体版本；不确定来源必须标注“待核验”。"
                )
                user_content = f"""请基于以下信息生成一份“拓展阅读材料”。
学生画像：{json.dumps(profile, ensure_ascii=False)}
需求单：{json.dumps(requirement, ensure_ascii=False)}
课程知识库参考：
{reference_text or "未检索到高相关参考，请仅基于确定知识生成，并标注待核验内容。"}

输出要求：
1. 只输出 Markdown，不要输出解释性前言。
2. 必须包含：阅读材料概览、入门阅读、案例阅读、进阶阅读、前沿阅读方向、阅读问题、阶段产出、7 天阅读安排、阅读后任务、学习成果评价标准、防幻觉与来源核验。
3. 每类阅读都要说明“适合解决的薄弱点、阅读方法、读后产物”，不要只列书名或资料名。"""

            elif spec.key == "mindmap":
                system = (
                    "你是知识结构建模智能体，负责把课程主题转成可解析的 Mermaid mindmap 和配套学习说明。"
                    "输出必须严谨，不要引入与课程无关的分支。"
                )
                user_content = f"""请基于以下信息生成一份“知识点思维导图”。
学生画像：{json.dumps(profile, ensure_ascii=False)}
需求单：{json.dumps(requirement, ensure_ascii=False)}
课程知识库参考：
{reference_text or "未检索到高相关参考，请仅基于确定知识生成。"}

输出要求：
1. 只输出 Markdown。
2. 必须先给一个 Mermaid mindmap 代码块，代码块内第一行必须是 mindmap。
3. Mermaid 使用 2 个空格表示层级，根节点为课程或章节名称；至少包含“核心概念、关键流程、易错点、练习路径、拓展方向”五个一级分支。
4. Mermaid 后补充“节点学习顺序”和“薄弱点定位说明”。"""

            elif spec.key == "quiz":
                quiz_types, quiz_counts, quiz_total = _quiz_generation_config(requirement)
                quiz_type_text = "、".join(f"{_QUIZ_TYPE_LABELS[item]} {quiz_counts[item]} 道" for item in quiz_types)
                system = (
                    "你是题库生成智能体，负责生成可被系统解析的个性化练习题。"
                    "必须严格遵守用户选择的题型和数量，只输出 JSON，不要输出 Markdown、注释或解释性前言。"
                )
                user_content = f"""请基于以下信息生成一份“个性化题库”。
学生画像：{json.dumps(profile, ensure_ascii=False)}
需求单：{json.dumps(requirement, ensure_ascii=False)}
课程知识库参考：
{reference_text or "未检索到高相关参考，请仅基于确定知识生成。"}

输出 JSON 结构必须为：
{{
  "meta": {{"course": "...", "chapter": "...", "weak_points": ["..."], "generated_by": "quiz"}},
  "questions": [{{"type": "题型英文标识", "stem": "题干", "options": ["A. 选项内容", "B. 选项内容"], "answer": "答案", "analysis": "解析", "difficulty": 1, "tags": ["知识点"]}}],
  "review_plan": ["..."]
}}

本次只能生成以下题型，禁止添加未选择的题型：{quiz_type_text}。
总题量必须为 {quiz_total} 道。选择题的每个选项必须是数组中的独立元素，只保留一个 A/B/C/D 标号，不得把多个选项拼成一行。代码必须放进题干中的独立代码围栏，并保留换行和缩进。题目必须围绕薄弱点递进。"""

            elif spec.key == "practice":
                system = (
                    "你是实操案例智能体，负责把课程知识转成可运行、可复现实操任务。"
                    "输出 Markdown，代码必须放在带语言标识的代码块中。"
                )
                user_content = f"""请基于以下信息生成一份“代码/实操案例”。
学生画像：{json.dumps(profile, ensure_ascii=False)}
需求单：{json.dumps(requirement, ensure_ascii=False)}
课程知识库参考：
{reference_text or "未检索到高相关参考，请仅基于确定知识生成。"}

输出要求：
1. 只输出 Markdown。
2. 必须包含：案例总览、环境准备、3 个由易到难的实操任务、完整代码或操作步骤、运行结果示例、常见错误与排查、扩展挑战、提交物要求。
3. 每个实操任务都要标注对应知识点、难度、预计耗时和验收标准。"""

            elif spec.key == "video":
                system = (
                    "你是多模态教学视频脚本智能体，负责生成可拍摄、可动画化的教学视频脚本。"
                    "输出 Markdown，重点体现画面、口播、动画和互动检查。"
                )
                user_content = f"""请基于以下信息生成一份“多模态视频/动画脚本”。
学生画像：{json.dumps(profile, ensure_ascii=False)}
需求单：{json.dumps(requirement, ensure_ascii=False)}
课程知识库参考：
{reference_text or "未检索到高相关参考，请仅基于确定知识生成。"}

输出要求：
1. 只输出 Markdown。
2. 必须包含：视频定位、目标观众、总时长、分镜表、关键画面设计、动画建议、口播稿、暂停互动题、素材清单、制作注意事项。
3. 分镜表至少 6 个镜头，每个镜头包含时间段、画面、动画/操作、口播、对应知识点。"""

            else:
                system = (
                    "你是多智能体系统中的一个角色。请根据需求单生成高质量学习资源。"
                    "输出应可直接用于大学生学习，结构清晰，可操作。"
                )
                user_content = f"""你的角色：{spec.title}
需求单：{json.dumps(requirement, ensure_ascii=False)}
学生画像：{json.dumps(profile, ensure_ascii=False)}
课程知识库参考：
{reference_text or "未检索到高相关参考。"}
请生成对应资源内容。"""

            content = await llm.chat_text(
                system=system,
                messages=[{"role": "user", "content": user_content}],
                temperature=0.6,
                on_chunk=on_chunk,
            )
            if spec.ext == "json":
                parsed = _parse_json_maybe(content)
                if parsed is not None:
                    if spec.key == "quiz":
                        parsed = _constrain_quiz_payload(parsed, requirement)
                    return json.dumps(parsed, ensure_ascii=False, indent=2)
                raise RuntimeError("模型返回的题库 JSON 格式异常，系统已停止保存损坏文件，请重新生成。")
            return content

        if use_glm:
            raise RuntimeError("多模态智能出题仅使用智谱 GLM，请先配置 GLM_TEXT_API_KEY 或 GLM_API_KEY")
        raise RuntimeError("内容生成模型尚未配置，本次没有生成模板资源或演示题库")

        wp = [str(x) for x in (requirement.get("weak_points") or [])]
        course = _safe_text(str(requirement.get("course", ""))) or "课程主题"
        chapter = _safe_text(str(requirement.get("chapter", ""))) or "当前章节"
        if spec.resource_type == "question_bank":
            qb = {
                "meta": {
                    "course": course,
                    "chapter": chapter,
                    "generated_by": spec.key,
                    "weak_points": wp,
                    "note": "未配置在线大模型：当前为结构化示例题库，配置 API 后可生成真实个性化题目。",
                },
                "questions": [
                    {
                        "type": "single_choice",
                        "stem": f"关于{chapter}的基础概念，下列说法哪一项最准确？",
                        "options": ["A. 能直接解释核心定义", "B. 与本章主题无关", "C. 只适用于个别特例", "D. 不需要结合例子理解"],
                        "answer": "A",
                        "analysis": "先确认概念定义，再结合题干判断适用范围。",
                        "difficulty": 1,
                        "tags": wp[:3],
                    },
                    {
                        "type": "multiple_choice",
                        "stem": f"学习{chapter}时，哪些做法有助于突破薄弱点？",
                        "options": ["A. 画出知识结构", "B. 只背结论不做题", "C. 用例子验证定义", "D. 记录错因并复盘"],
                        "answer": ["A", "C", "D"],
                        "analysis": "结构化、例证化和错因复盘能同时补概念与应用。",
                        "difficulty": 2,
                        "tags": wp[:3],
                    },
                    {
                        "type": "blank",
                        "stem": f"请写出{chapter}中一个你最容易混淆的关键词，并说明它和相近概念的区别。",
                        "answer": "填写关键词与区别说明。",
                        "analysis": "该题用于暴露概念边界不清的问题。",
                        "difficulty": 2,
                        "tags": wp[:3],
                    },
                    {
                        "type": "short_answer",
                        "stem": f"请用 3 个步骤说明如何分析一道{chapter}相关题目。",
                        "answer": "识别知识点；套用定义/流程；检查边界条件和易错点。",
                        "analysis": "分步回答能检验是否掌握可迁移的方法。",
                        "difficulty": 3,
                        "tags": wp[:3],
                    },
                    {
                        "type": "case_analysis",
                        "stem": f"给定一个{course}场景，请说明如何把{chapter}知识应用到实际问题中。",
                        "answer": "先抽取场景要素，再匹配知识点，最后给出判断和改进方案。",
                        "analysis": "案例题用于检查知识迁移能力。",
                        "difficulty": 4,
                        "tags": wp[:3],
                    }
                ],
                "review_plan": [
                    "先完成基础选择题，确认概念边界。",
                    "再完成简答和案例题，检查迁移能力。",
                    "把错题按薄弱点归类，进入下一轮资源推送。",
                ],
            }
            return json.dumps(qb, ensure_ascii=False, indent=2)

        header = f"# {spec.title}\n"
        body = "\n".join(
            [
                "## 需求摘要",
                f"- 课程：{course}",
                f"- 章节：{chapter}",
                f"- 薄弱点：{', '.join(wp) if wp else '待补充'}",
                "",
                "## 内容",
                "未配置在线大模型：这里输出可编辑的资源骨架，填入模型后可一键重新生成。",
            ]
        )
        if reference_text:
            body += "\n\n## 知识库参考片段\n" + reference_text + "\n"
        if spec.resource_type == "mindmap":
            root = chapter if chapter != "当前章节" else course
            body += f"""\n\n```mermaid
mindmap
  root(({root}))
    核心概念
      定义
      适用场景
      相近概念对比
    关键流程
      识别问题
      选择方法
      验证结果
    易错点
      {wp[0] if wp else "概念边界不清"}
      {wp[1] if len(wp) > 1 else "步骤遗漏"}
    练习路径
      基础题
      综合题
      案例题
    拓展方向
      工程应用
      前沿问题
```

## 节点学习顺序
1. 先学核心概念，明确定义和边界。
2. 再看关键流程，把知识转成可执行步骤。
3. 最后用练习路径检查薄弱点是否真正解决。
"""
        if spec.resource_type == "practice_case":
            body += f"""\n\n## 实操任务 1：概念验证
- 难度：基础
- 预计耗时：20 分钟
- 对应知识点：{chapter}
- 目标：用最小示例验证核心定义。
- 验收标准：能解释输入、处理过程和输出结果。

## 实操任务 2：错误排查
- 难度：中等
- 预计耗时：30 分钟
- 对应知识点：{', '.join(wp[:2]) if wp else chapter}
- 目标：构造一个常见错误，并写出排查步骤。
- 验收标准：能定位错因并给出修正方案。

## 实操任务 3：小型综合案例
- 难度：提高
- 预计耗时：45 分钟
- 对应知识点：{course}
- 目标：把本章方法应用到一个真实学习或工程场景。
- 验收标准：提交结果、过程记录和复盘说明。
"""
        if spec.resource_type == "video_script":
            body += f"""\n\n## 视频定位
- 目标观众：正在学习 {course} 的学生
- 总时长：6 到 8 分钟
- 解决问题：{', '.join(wp) if wp else chapter}

## 分镜表
| 时间段 | 画面 | 动画/操作 | 口播重点 | 对应知识点 |
|---|---|---|---|---|
| 00:00-00:30 | 展示本节问题 | 高亮关键词 | 说明为什么要学 | 学习目标 |
| 00:30-01:30 | 概念关系图 | 节点逐个出现 | 给出直观解释 | 核心概念 |
| 01:30-03:00 | 流程拆解 | 步骤推进 | 讲清分析顺序 | 关键流程 |
| 03:00-04:30 | 例题/案例 | 边做边标注 | 演示应用方法 | 实例迁移 |
| 04:30-05:30 | 易错对比 | 正误并排 | 解释错因 | 薄弱点 |
| 05:30-06:30 | 自测题 | 暂停提示 | 引导学生作答 | 学习评估 |
"""
        if spec.resource_type == "reading":
            body += f"""\n\n## 拓展阅读安排
| 层级 | 读什么 | 解决什么问题 | 阅读产出 |
|---|---|---|---|
| 入门阅读 | 教材中与 {chapter} 对应的基础章节 | 建立概念框架 | 5 条概念卡片 |
| 案例阅读 | 与 {course} 应用场景相关的案例材料 | 理解知识如何落地 | 1 份案例拆解表 |
| 进阶阅读 | 方法比较、复杂场景或综合题解析 | 提高迁移能力 | 1 张方法对比表 |
| 前沿方向 | 课程相关的新工具、新技术或工程实践 | 扩展视野 | 3 个可继续探索的问题 |

## 阅读后任务
- 用自己的话复述本章核心概念。
- 标出仍然不清楚的 2 个问题，交给智能辅导继续追问。
- 把阅读产物加入下一轮学习路径规划。
"""
        return header + body + "\n"
