from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import re
from typing import Any

from app.core.config import settings
from app.llm import is_llm_configured
from app.repo import (
    get_latest_profile_snapshot,
    get_user_dir,
    get_user_events,
    get_user_usages,
    list_resources,
    read_json,
)
from app.services.knowledge_hub import mastery_data, overview as knowledge_overview
from app.services.path_progress import overlay_path_progress


PROFILE_DIMENSIONS = [
    ("knowledge_base_level", "知识基础", "当前课程基础与概念掌握水平"),
    ("cognitive_style", "认知风格", "理解、组织和迁移知识的主要方式"),
    ("mistake_patterns", "易错模式", "反复出现的概念混淆或解题偏差"),
    ("modality_preference", "模态偏好", "更有效的内容表达与交互形式"),
    ("pace_preference", "学习节奏", "适合的讲解密度、步长和复习频率"),
    ("motivation_style", "动机类型", "维持投入和完成目标的驱动力"),
]

PROFILE_TEXT_TRANSLATIONS = {
    "unknown": "待识别",
    "not specified": "尚未识别",
    "beginner": "初学阶段",
    "low": "基础薄弱",
    "intermediate": "中等水平",
    "undergraduate": "本科阶段",
    "beginner to intermediate": "初学到中等水平",
    "sequential": "循序型",
    "concrete": "具体理解型",
    "visual": "视觉型",
    "text": "文字型",
    "moderate": "中等节奏",
    "slow": "慢节奏",
    "intrinsic": "内在驱动型",
    "extrinsic": "外部激励型",
    "corrective": "纠错驱动型",
    "exploration": "探索驱动型",
    "problem-solving": "问题解决型",
    "goal-oriented": "目标导向型",
    "mastery-oriented": "掌握导向型",
    "none observed": "暂未发现明显错误",
    "unable to parse user input": "暂时无法识别输入内容",
    "lack of clarity": "学习目标不够明确",
    "need more details": "学习信息尚待补充",
    "software engineering": "软件工程",
    "weak": "基础薄弱",
    "java basics": "Java 基础",
    "object-oriented concepts": "面向对象概念",
    "syntax specifics": "Java 语法细节",
    "undergraduate, weak in java": "本科阶段，Java 基础薄弱",
    "undergraduate, very weak in java basics and c, struggling with uml and software engineering concepts": "本科阶段，Java 与 C 语言基础较薄弱，对 UML 和软件工程概念掌握不足",
    "concrete_sequential with step-by-step interactive guidance": "具体、循序型，适合分步骤互动指导",
    "common java pitfalls (null pointer, type confusion, improper exception handling)": "常见 Java 易错点：空指针、类型混淆与异常处理不当",
    "visual with concrete diagrams and examples": "视觉型，偏好具体图解与实例",
    "extrinsic (建议基于低分和反复错误，需要外部激励和成就感重建)": "外部激励型，建议通过阶段成果和正向反馈重建成就感",
    "slow (基于反复错误推测需要较慢节奏)": "慢节奏，适合分步骤讲解并加强复习",
    "overlooking fundamentals, asking for self-introduction repeatedly": "容易忽视基础知识，并重复询问自我介绍相关问题",
    "text with examples": "文字讲解结合实例",
    "slower, step-by-step": "较慢节奏，适合分步骤学习",
    "external guidance + achievement-oriented": "外部指导与成就目标驱动型",
    "self-introduction confusion": "自我介绍相关概念易混淆",
    "resource dissatisfaction": "对当前学习资源不满意",
    "needs step-by-step guidance": "需要分步骤指导",
    "java learning": "Java 学习",
    "fundamental": "基础知识",
    "self-introduction": "自我介绍",
}

PROFILE_PHRASE_TRANSLATIONS = (
    (r"\bneed more details\b", "学习信息尚待补充"),
    (r"\bjava basics\b", "Java 基础"),
    (r"\bobject-oriented concepts\b", "面向对象概念"),
    (r"\bsyntax specifics\b", "Java 语法细节"),
    (r"\bsoftware engineering\b", "软件工程"),
    (r"\bnull pointer\b", "空指针"),
    (r"\btype confusion\b", "类型混淆"),
    (r"\bimproper exception handling\b", "异常处理不当"),
    (r"\bconcrete[_ -]sequential\b", "具体、循序型"),
    (r"\bvisual\b", "视觉型"),
    (r"\bslow\b", "慢节奏"),
    (r"\bextrinsic\b", "外部激励型"),
    (r"\bweak\b", "基础薄弱"),
    (r"\bbeginner\s+to\s+intermediate\b", "初学到中等水平"),
    (r"\bself[- ]introduction\s+confusion\b", "自我介绍相关概念易混淆"),
    (r"\bself[- ]introduction\b", "自我介绍"),
    (r"\bresource\s+dissatisfaction\b", "对当前学习资源不满意"),
    (r"\bneeds?\s+step[- ]by[- ]step\s+guidance\b", "需要分步骤指导"),
    (r"\bstep[- ]by[- ]step\b", "分步骤"),
    (r"\boverlooking\s+fundamentals\b", "容易忽视基础知识"),
    (r"\btext\s+with\s+examples\b", "文字讲解结合实例"),
    (r"\bexternal\s+guidance\b", "外部指导"),
    (r"\bachievement[- ]oriented\b", "成就目标驱动型"),
    (r"\bjava\s+learning\b", "Java 学习"),
    (r"\bfundamentals?\b", "基础知识"),
)

PROFILE_TRIGGER_LABELS = {
    "mastery_low_score": "知识掌握度偏低",
    "negative_feedback": "学习资源负反馈",
    "manual_evaluation_review": "人工评估复盘",
    "repeated_tutor_question": "重复辅导提问",
    "exercise_diagnosis": "练习诊断",
    "profile_chat": "画像对话",
    "resource_feedback": "资源使用反馈",
}

RESOURCE_LABELS = {
    "lecture_doc": "讲解文档",
    "mindmap": "思维导图",
    "question_bank": "个性题库",
    "reading": "拓展阅读",
    "practice_case": "实操案例",
    "video_script": "视频脚本",
    "quality_check": "质量审计",
}

EVENT_LABELS = {
    "profile_update": ("画像已更新", "新的学习证据已写入六维画像", "profile"),
    "generate": ("资源已生成", "多智能体完成一轮资源协作", "resource"),
    "clarify": ("需求已澄清", "资源工坊完成学习需求结构化", "resource"),
    "knowledge_search": ("知识检索", "已从课程知识库检索相关证据", "knowledge"),
    "path_plan": ("路径已规划", "系统根据画像与行为重排学习步骤", "path"),
    "tutor": ("辅导对话", "智能辅导记录了新的学习问题", "tutor"),
    "evaluate": ("完成评估", "学习证据已汇总为效果评估", "evaluate"),
    "evolution_triggered": ("策略已进化", "画像和推荐策略已按新证据调整", "evolution"),
    "evolution_skipped": ("保持当前策略", "证据不足，暂不改变当前画像", "evolution"),
    "exercise_answer": ("练习已诊断", "答题结果已进入学习闭环", "exercise"),
}


def learning_overview(student_id: str) -> dict[str, Any]:
    llm_ready = any(is_llm_configured(use_case) for use_case in ("profile", "generate", "plan", "tutor", "evaluate"))
    profile = profile_overview(student_id)
    workshop = workshop_overview(student_id)
    evaluation = evaluation_overview(student_id)
    path = path_overview(student_id)
    tutor = tutor_overview(student_id)
    events = get_user_events(student_id)
    usages = get_user_usages(student_id)

    weak_points = profile["focus"]["weak_points"]
    primary_focus = weak_points[0] if weak_points else "建立当前课程的核心概念地图"
    profile_ready = profile["completeness"] >= 60
    resource_ready = workshop["total"] > 0
    practice_ready = evaluation["evidence"]["exercise_attempts"] > 0
    knowledge_ready = evaluation["evidence"]["knowledge_nodes"] > 0
    path_ready = path["has_plan"]
    tutor_ready = tutor["session_count"] > 0
    evaluate_ready = evaluation["evidence"]["total"] >= 2
    evolved = any(e.get("event_type") == "evolution_triggered" for e in events)

    journey = [
        _journey_item("profile", "用户画像", "/profile", profile_ready, profile["completeness"], "画像完整度"),
        _journey_item("resource", "资源生成", "/workshop", resource_ready, workshop["total"], "份学习资源"),
        _journey_item("exercise", "练习诊断", "/exercise", practice_ready, evaluation["evidence"]["exercise_attempts"], "次答题证据"),
        _journey_item("knowledge", "知识中枢", "/knowledge", knowledge_ready, evaluation["evidence"]["knowledge_nodes"], "个跟踪节点"),
        _journey_item("path", "路径推送", "/path", path_ready, path["stage_count"], "个学习阶段"),
        _journey_item("tutor", "智能辅导", "/tutor", tutor_ready, tutor["session_count"], "条有效提问"),
        _journey_item("evaluate", "评估进化", "/evaluate", evaluate_ready, evaluation["score"], "综合分"),
        _journey_item("evolution", "策略迭代", "/evaluate", evolved, len(profile["history"]), "版画像证据"),
    ]

    next_actions = _next_actions(
        profile_ready=profile_ready,
        resource_ready=resource_ready,
        practice_ready=practice_ready,
        path_ready=path_ready,
        evaluate_ready=evaluate_ready,
        focus=primary_focus,
    )
    completed = len([item for item in journey if item["status"] == "done"])

    return {
        "learner": profile["learner"],
        "focus": {
            **profile["focus"],
            "primary": primary_focus,
            "recommended_action": next_actions[0]["title"],
        },
        "metrics": [
            {"key": "loop", "label": "闭环进度", "value": round(completed / len(journey) * 100), "unit": "%", "tone": "primary"},
            {"key": "resources", "label": "资源成果", "value": workshop["total"], "unit": "份", "tone": "indigo"},
            {"key": "mastery", "label": "知识掌握", "value": evaluation["mastery"], "unit": "%", "tone": "cyan"},
            {"key": "evidence", "label": "有效证据", "value": evaluation["evidence"]["total"], "unit": "条", "tone": "amber"},
        ],
        "journey": journey,
        "next_actions": next_actions,
        "activity": activity_feed(student_id, limit=8),
        "system": {
            "demo_mode": not llm_ready,
            "llm_configured": llm_ready,
            "resource_feedback_count": len(usages),
            "last_event_at": events[-1].get("created_at", "") if events else "",
            "health": "ready",
        },
    }


def profile_overview(student_id: str) -> dict[str, Any]:
    user_dir = get_user_dir(student_id)
    learner = read_json(user_dir / "student.json", {}) or {"id": student_id}
    snapshots = read_json(user_dir / "profiles.json", []) or []
    snapshots = sorted(snapshots, key=lambda item: item.get("created_at", ""), reverse=True)
    latest = snapshots[0] if snapshots else (get_latest_profile_snapshot(student_id) or {})
    evidence = latest.get("evidence") or {}
    weak_points = [_localize_profile_text(item) for item in _string_list(evidence.get("weak_points"))]
    keywords = [_localize_profile_text(item) for item in _string_list(evidence.get("keywords"))]
    values_present = sum(1 for key, _, _ in PROFILE_DIMENSIONS if str(latest.get(key, "")).strip())
    evidence_bonus = min(18, len(weak_points) * 3 + len(keywords))
    completeness = min(98, round(values_present / len(PROFILE_DIMENSIONS) * 80 + evidence_bonus))

    dimensions = []
    for key, label, description in PROFILE_DIMENSIONS:
        value = _localize_profile_text(latest.get(key, "") or "待识别")
        confidence = _profile_dimension_confidence(latest, key)
        dimensions.append(
            {
                "key": key,
                "label": label,
                "value": value,
                "description": description,
                "confidence": confidence,
                "status": "ready" if value != "待识别" else "pending",
            }
        )

    history = [
        {
            "id": item.get("id", f"profile-{idx}"),
            "version": f"v{len(snapshots) - idx}.0",
            "created_at": item.get("created_at", ""),
            "reason": _profile_change_reason(item),
        }
        for idx, item in enumerate(snapshots[:6])
    ]
    previous = snapshots[1] if len(snapshots) > 1 else {}
    changes = []
    if previous:
        for key, label, _ in PROFILE_DIMENSIONS:
            before = _localize_profile_text(previous.get(key, "") or "")
            after = _localize_profile_text(latest.get(key, "") or "")
            if before != after:
                changes.append({"key": key, "label": label, "before": before, "after": after})

    return {
        "learner": {
            "student_id": student_id,
            "display_name": learner.get("name") or student_id,
            "major": _localize_profile_text(learner.get("major") or ""),
            "grade": learner.get("grade") or "",
            "current_course": _localize_profile_text(learner.get("current_course") or learner.get("course") or ""),
            "goals": learner.get("goals") or "",
            "profile_version": history[0]["version"] if history else "v0.1",
            "updated_at": latest.get("created_at", learner.get("created_at", "")),
        },
        "completeness": completeness,
        "dimensions": dimensions,
        "focus": {
            "weak_points": weak_points,
            "keywords": keywords,
            "headline": _focus_headline(weak_points, keywords),
        },
        "history": history,
        "comparison": {
            "previous_dimensions": {
                key: _profile_dimension_confidence(previous, key)
                for key, _, _ in PROFILE_DIMENSIONS
            } if previous else {},
            "changes": changes,
        },
        "evidence_count": len(weak_points) + len(keywords) + len(evidence.get("evolution_records") or []),
        "snapshot": latest,
    }


def workshop_overview(student_id: str) -> dict[str, Any]:
    resources = [
        item for item in list_resources(student_id)
        if str((((item.get("meta") or {}).get("requirement") or {}).get("constraints") or {}).get("source") or "")
        != "exercise_custom_bank"
        and str(item.get("type") or "") not in {"multimodal_plan", "multimodal_video", "tutor_session"}
    ]
    counts = Counter(str(item.get("type", "unknown")) for item in resources)
    latest = [_resource_summary(item) for item in resources[:12]]
    audits = [item for item in resources if item.get("type") == "quality_check"]
    latest_audit = audits[0].get("meta", {}).get("audit", {}) if audits else {}
    risk_score = _number(latest_audit.get("risk_score"), 0)
    return {
        "total": len(resources),
        "type_count": len([key for key, count in counts.items() if count and key != "quality_check"]),
        "distribution": [
            {"type": key, "label": RESOURCE_LABELS.get(key, key), "count": count}
            for key, count in counts.most_common()
        ],
        "latest": latest,
        "quality": {
            "status": str(latest_audit.get("overall_status") or ("ready" if resources else "pending")),
            "risk_score": risk_score,
            "summary": str(latest_audit.get("summary") or "生成结果会经过结构、引用与幻觉风险检查。"),
        },
        "agents": [
            {"key": "planner", "label": "需求规划", "role": "将自然语言转成可执行需求单"},
            {"key": "knowledge", "label": "知识检索", "role": "绑定课程资料与可追溯证据"},
            {"key": "creator", "label": "内容生成", "role": "按资源类型并行组织学习内容"},
            {"key": "reviewer", "label": "质量审计", "role": "检查结构、引用和潜在幻觉"},
        ],
    }


def knowledge_workspace(student_id: str) -> dict[str, Any]:
    summary = knowledge_overview(student_id)
    mastery = mastery_data(student_id)
    return {
        "summary": summary,
        "mastery": mastery,
        "focus": _knowledge_focus(mastery),
        "actions": [
            {"label": "定位薄弱节点", "action": "weak"},
            {"label": "生成学习路径", "action": "path"},
            {"label": "检索课程证据", "action": "search"},
        ],
    }


def path_overview(student_id: str) -> dict[str, Any]:
    events = [item for item in get_user_events(student_id) if item.get("event_type") == "path_plan"]
    latest = events[-1] if events else {}
    payload = latest.get("payload") or {}
    raw_path = payload.get("path") or payload.get("plan") or {}
    path = raw_path if isinstance(raw_path, dict) else {}
    nodes = _normalize_path_nodes(path.get("nodes") or path.get("steps") or payload.get("nodes") or [])
    nodes, progress = overlay_path_progress(
        student_id,
        plan_key=str(latest.get("id") or latest.get("created_at") or ""),
        nodes=nodes,
    )
    branches = [branch for node in nodes for branch in (node.get("branches") or []) if isinstance(branch, dict)]
    resources = [_resource_summary(item) for item in list_resources(student_id)[:6]]
    rules = _string_list(path.get("dynamic_rules") or path.get("rules") or payload.get("rules"))
    return {
        "has_plan": bool(events and nodes),
        "title": payload.get("title") or path.get("title") or "",
        "updated_at": latest.get("created_at", ""),
        "stage_count": len(nodes),
        "current_stage": next((item for item in nodes if item.get("status") in {"current", "active", "warning"}), nodes[-1] if nodes else {}),
        "nodes": nodes,
        "branches": branches,
        "progress": progress,
        "recommendations": resources,
        "strategy": _string_list(path.get("strategy") or payload.get("strategy")),
        "rationale": str(path.get("rationale") or payload.get("rationale") or ""),
        "rules": rules,
    }


def tutor_overview(student_id: str) -> dict[str, Any]:
    events = [item for item in get_user_events(student_id) if item.get("event_type") == "tutor"]
    questions = [str((item.get("payload") or {}).get("question", "")).strip() for item in events]
    questions = [item for item in questions if item]
    profile = profile_overview(student_id)
    weak_points = profile["focus"]["weak_points"]
    suggested = [
        f"请用对比表和案例解释：{weak_points[0]}" if weak_points else "请帮我定位当前课程最需要先补的概念",
        "把刚才的知识点拆成 3 个由浅入深的检查问题",
        "请基于课程知识库回答，并明确标出证据边界",
    ]
    return {
        "session_count": len(questions),
        "recent_questions": questions[-6:][::-1],
        "suggested_questions": suggested,
        "capabilities": ["课程知识库检索", "分步讲解", "追问澄清", "会话证据回写"],
        "boundary": "回答优先使用本地课程知识库；证据不足时会明确说明，不编造来源。",
    }


def evaluation_overview(student_id: str) -> dict[str, Any]:
    user_dir = get_user_dir(student_id)
    exercise_records = read_json(user_dir / "exercise_records.json", []) or []
    knowledge_state = read_json(user_dir / "knowledge_state.json", {}) or {}
    resources = list_resources(student_id)
    usages = get_user_usages(student_id)
    events = get_user_events(student_id)
    latest_report: dict[str, Any] | None = None
    for event in reversed(events):
        if event.get("event_type") != "evaluate":
            continue
        candidate = (event.get("payload") or {}).get("report")
        if isinstance(candidate, dict):
            latest_report = candidate
            break

    answered = [item for item in exercise_records if item.get("answer") not in (None, "", [])]
    correct = len([item for item in answered if item.get("correct") is True])
    accuracy = round(correct / len(answered) * 100, 1) if answered else 0
    node_states = list((knowledge_state.get("nodes") or {}).values())
    mastery = round(sum(_number(item.get("mastery"), 0) for item in node_states) / len(node_states), 1) if node_states else 0
    engagement = min(100, len(resources) * 3 + len(usages) * 8 + len(events) * 2)
    evidence_total = len(answered) + len(node_states) + len(usages) + len(resources) + len(events)
    resource_match = round(len(usages) * 100 / len(resources), 1) if resources else 0
    strategy_stability = min(100, len([event for event in events if event.get("event_type") in {"path_plan", "evaluate", "evolution_triggered"}]) * 20)
    score = round(accuracy * 0.35 + mastery * 0.35 + engagement * 0.2 + resource_match * 0.1) if evidence_total else 0
    wrong_tags = Counter(
        tag
        for item in answered
        if not item.get("correct")
        for tag in _string_list(item.get("tags"))
    )
    weak_points = [tag for tag, _ in wrong_tags.most_common(5)]
    if not weak_points:
        weak_points = profile_overview(student_id)["focus"]["weak_points"][:5]

    return {
        "score": min(100, max(0, score)),
        "mastery": mastery,
        "accuracy": accuracy,
        "engagement": engagement,
        "weak_points": weak_points,
        "evidence": {
            "total": evidence_total,
            "exercise_attempts": len(answered),
            "knowledge_nodes": len(node_states),
            "resource_items": len(resources),
            "feedback_items": len(usages),
            "learning_events": len(events),
        },
        "confidence": _evaluation_confidence(evidence_total),
        "dimensions": [
            {"label": "知识掌握", "value": mastery},
            {"label": "迁移应用", "value": round(accuracy * 0.88, 1)},
            {"label": "学习投入", "value": engagement},
            {"label": "资源匹配", "value": resource_match},
            {"label": "策略稳定", "value": strategy_stability},
        ],
        "suggestions": _evaluation_suggestions(weak_points, accuracy, mastery),
        "timeline": activity_feed(student_id, limit=10),
        "latest_report": latest_report,
    }


def activity_feed(student_id: str, limit: int = 8) -> list[dict[str, Any]]:
    events = get_user_events(student_id)
    result: list[dict[str, Any]] = []
    for event in events[-limit:][::-1]:
        event_type = str(event.get("event_type", ""))
        title, detail, tone = EVENT_LABELS.get(event_type, ("学习行为", "新的学习证据已记录", "neutral"))
        payload = event.get("payload") or {}
        result.append(
            {
                "id": event.get("id", ""),
                "type": event_type,
                "title": title,
                "detail": _event_detail(detail, payload),
                "tone": tone,
                "created_at": event.get("created_at", ""),
            }
        )
    return result


def _journey_item(key: str, label: str, route: str, done: bool, value: int | float, unit: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "route": route,
        "status": "done" if done else "next",
        "value": value,
        "evidence": f"{value}{unit}",
    }


def _next_actions(
    *,
    profile_ready: bool,
    resource_ready: bool,
    practice_ready: bool,
    path_ready: bool,
    evaluate_ready: bool,
    focus: str,
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    candidates = [
        (not profile_ready, "补全六维学习画像", "用一段自然语言描述课程、目标和学习偏好。", "/profile", "完善画像"),
        (not resource_ready, f"为“{focus}”生成资源包", "让多智能体同时生成讲解、导图、题库和审计报告。", "/workshop", "生成资源"),
        (not practice_ready, "完成一次诊断练习", "用真实答题证据校准当前薄弱点。", "/exercise", "开始练习"),
        (not path_ready, "生成本周个性化路径", "把画像、资源和诊断结果组织成可执行步骤。", "/path", "规划路径"),
        (not evaluate_ready, "生成学习效果评估", "查看证据链、薄弱项与策略调整建议。", "/evaluate", "查看评估"),
        (True, f"继续突破：{focus}", "进入智能辅导，用追问把概念边界讲清楚。", "/tutor", "开始辅导"),
    ]
    for condition, title, description, route, cta in candidates:
        if condition:
            actions.append({"title": title, "description": description, "route": route, "cta": cta})
        if len(actions) == 3:
            break
    return actions


def _resource_summary(item: dict[str, Any]) -> dict[str, Any]:
    resource_type = str(item.get("type", "unknown"))
    meta = item.get("meta") or {}
    requirement = meta.get("requirement") or {}
    uri = str(item.get("content_uri", ""))
    return {
        "id": item.get("id", ""),
        "type": resource_type,
        "type_label": RESOURCE_LABELS.get(resource_type, resource_type),
        "title": item.get("title") or RESOURCE_LABELS.get(resource_type, "学习资源"),
        "tags": _string_list(item.get("tags"))[:5],
        "created_at": item.get("created_at", ""),
        "preview_url": f"/{uri.lstrip('/')}" if uri else "",
        "course": requirement.get("course", ""),
        "chapter": requirement.get("chapter", ""),
        "agent": meta.get("agent", "resource_agent"),
    }


def _fallback_path_nodes(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    resource_titles = [item.get("title", "") for item in resources]
    return [
        {"id": "diagnose", "step": 1, "title": "先修诊断", "goal": "确认概念边界与真实薄弱点", "status": "completed", "checkpoint": "完成画像与诊断证据采集", "resources": resource_titles[:1], "tasks": ["查看画像证据"]},
        {"id": "concept", "step": 2, "title": "概念补齐", "goal": "用图解和对比建立准确概念模型", "status": "current", "checkpoint": "能够解释核心概念差异", "resources": resource_titles[:2], "tasks": ["精读讲解", "复述概念"]},
        {"id": "model", "step": 3, "title": "案例建模", "goal": "把抽象方法应用到真实业务场景", "status": "locked", "checkpoint": "完成一份可检查的建模产物", "resources": resource_titles[2:4], "tasks": ["分析案例", "提交模型"]},
        {"id": "transfer", "step": 4, "title": "迁移强化", "goal": "通过变式问题验证知识迁移能力", "status": "locked", "checkpoint": "综合任务达到 80 分", "resources": resource_titles[4:6], "tasks": ["完成综合练习"]},
        {"id": "review", "step": 5, "title": "评估进化", "goal": "汇总证据并调整下一轮策略", "status": "locked", "checkpoint": "生成学习效果报告", "resources": [], "tasks": ["查看证据链"]},
    ]


def _normalize_path_nodes(raw_nodes: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_nodes, list):
        return []
    nodes: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_nodes):
        if not isinstance(raw, dict):
            continue
        step = raw.get("step") or raw.get("order") or index + 1
        nodes.append(
            {
                **raw,
                "id": raw.get("id") or f"stage-{step}",
                "step": step,
                "title": raw.get("title") or raw.get("objective") or f"学习阶段 {step}",
                "goal": raw.get("goal") or raw.get("objective") or "",
                "resources": raw.get("resources") if isinstance(raw.get("resources"), list) else [],
                "tasks": raw.get("tasks") if isinstance(raw.get("tasks"), list) else [],
                "checkpoint": raw.get("checkpoint") or raw.get("assessment") or "",
                "status": raw.get("status") or ("current" if not nodes else "locked"),
            }
        )
    return nodes


def _evaluation_suggestions(weak_points: list[str], accuracy: float, mastery: float) -> list[dict[str, str]]:
    focus = weak_points[0] if weak_points else "当前课程核心概念"
    suggestions = [
        {"title": f"优先修复“{focus}”", "detail": "使用对比图、正反例和一次可检查的案例任务形成闭环。", "route": "/workshop"},
        {"title": "把答疑转成可追踪证据", "detail": "完成辅导后保存会话，让重复问题自动进入画像进化判断。", "route": "/tutor"},
    ]
    if accuracy < 70:
        suggestions.insert(1, {"title": "降低练习步长", "detail": "先做概念辨析，再进入案例分析，避免直接跳到综合任务。", "route": "/exercise"})
    elif mastery < 70:
        suggestions.insert(1, {"title": "补充知识节点复习", "detail": "从知识图谱定位低掌握节点并安排间隔复习。", "route": "/knowledge"})
    return suggestions[:3]


def _knowledge_focus(mastery: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = mastery.get("weak_nodes") or mastery.get("nodes") or []
    if isinstance(candidates, dict):
        candidates = list(candidates.values())
    return [
        {"id": item.get("id", ""), "name": item.get("name") or item.get("title") or "知识节点", "mastery": _number(item.get("mastery") or item.get("current_mastery"), 0)}
        for item in candidates[:6]
        if isinstance(item, dict)
    ]


def _profile_change_reason(snapshot: dict[str, Any]) -> str:
    records = (snapshot.get("evidence") or {}).get("evolution_records") or []
    if records:
        trigger = str(records[-1].get("trigger", "学习行为"))
        trigger_label = PROFILE_TRIGGER_LABELS.get(trigger, _localize_profile_text(trigger))
        return f"因{trigger_label}而更新画像"
    return "由画像对话与学习证据生成"


def _localize_profile_text(value: Any) -> str:
    text = " ".join(str(value or "").strip().split())
    if not text:
        return ""
    exact = PROFILE_TEXT_TRANSLATIONS.get(text.casefold())
    if exact:
        return exact
    localized = text
    for pattern, replacement in PROFILE_PHRASE_TRANSLATIONS:
        localized = re.sub(pattern, replacement, localized, flags=re.IGNORECASE)
    localized = localized.replace("_", " ")
    technical_terms = r"\b(?:Java|UML|SQL|JDBC|HTTP|TCP|UDP|API|I/O|C\+\+|C)\b"
    residual = re.sub(technical_terms, "", localized, flags=re.IGNORECASE)
    if re.search(r"[A-Za-z]{2,}", residual):
        chinese_only = re.sub(r"\b[A-Za-z][A-Za-z0-9+./-]*\b", "", localized)
        chinese_only = re.sub(r"\s*[,;+]\s*", "，", chinese_only)
        chinese_only = re.sub(r"\s+", " ", chinese_only).strip(" ，、+-")
        if re.search(r"[\u4e00-\u9fff]", chinese_only):
            return chinese_only
        return "已识别的学习特征"
    return localized


def _profile_dimension_confidence(snapshot: dict[str, Any], key: str) -> int:
    """Estimate confidence only from persisted evidence attached to this snapshot."""
    if not str(snapshot.get(key, "")).strip():
        return 0
    evidence = snapshot.get("evidence") or {}
    source_count = len(_string_list(evidence.get("weak_points")))
    source_count += len(_string_list(evidence.get("keywords")))
    source_count += len(evidence.get("evolution_records") or [])
    source_count += 1 if str(evidence.get("user_text", "")).strip() else 0
    return min(95, 50 + source_count * 5)


def _evaluation_confidence(evidence_total: int) -> dict[str, Any]:
    if evidence_total <= 0:
        return {"level": "none", "label": "暂无证据", "evidence_total": 0}
    if evidence_total < 5:
        return {"level": "low", "label": "较低", "evidence_total": evidence_total}
    if evidence_total < 15:
        return {"level": "medium", "label": "中", "evidence_total": evidence_total}
    return {"level": "high", "label": "高", "evidence_total": evidence_total}


def _focus_headline(weak_points: list[str], keywords: list[str]) -> str:
    if weak_points:
        return f"当前优先突破：{weak_points[0]}"
    if keywords:
        return f"围绕“{keywords[0]}”建立可迁移的知识结构"
    return "先补全学习目标与薄弱点，系统将据此生成个性化闭环"


def _event_detail(default: str, payload: dict[str, Any]) -> str:
    for key in ("question", "title", "topic", "reason"):
        value = str(payload.get(key, "")).strip()
        if value:
            return value[:96]
    return default


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.replace("；", ",").replace("、", ",").split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _number(value: Any, fallback: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def generated_at() -> str:
    return datetime.now(timezone.utc).isoformat()
